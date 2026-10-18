// SPDX-License-Identifier: MPL-2.0
#include <config.h>

#include "backend_support.h"

#include <cstdint>
#include <dhcp/libdhcp++.h>
#include <dhcp/option_space.h>
#include <dhcpsrv/cfg_option_def.h>
#include <dhcpsrv/config_backend_dhcp4_mgr.h>
#include <dhcpsrv/parsers/dhcp_parsers.h>
#include <dhcpsrv/parsers/option_data_parser.h>
#include <map>
#include <set>
#include <sys/socket.h>

namespace kea_db_commands {
namespace {
using namespace isc::data;
using namespace isc::db;
using namespace isc::dhcp;
using namespace isc::config;
enum class Operation : std::uint8_t { List, Get, Set, Del };

ServerTag optionTag(const ConstElementPtr& arguments) {
    const auto field =
        optionalField(arguments, "server-tag", Element::string, "server-tag must be a string.");
    if (!field || field->stringValue().find('\0') != std::string::npos) {
        throw ContractError("An explicit server-tag without NUL is required.");
    }
    const auto tag = validatedServerTag(field->stringValue());
    if (tag.get() == "any") {
        throw ContractError("The any selector is unsupported.");
    }
    return tag;
}

void identity(const ConstElementPtr& object) {
    const auto code =
        optionalField(object, "code", Element::integer, "code must be an integer in 1..254.");
    const auto space =
        optionalField(object, "space", Element::string, "space must be an explicit option space.");
    if (!code || code->intValue() < 1 || code->intValue() > 254) {
        throw ContractError("code must be an integer in 1..254.");
    }
    if (!space || space->stringValue().size() > 128 ||
        space->stringValue().find('\0') != std::string::npos || space->stringValue() == "dhcp6" ||
        !OptionSpace::validateName(space->stringValue())) {
        throw ContractError("space must be a valid DHCPv4 option space of at most 128 bytes.");
    }
}

void typedFields(const ConstElementPtr& object) {
    for (const auto* name : {"name", "type", "record-types", "encapsulate", "data"}) {
        const auto value =
            optionalField(object, name, Element::string, "Option text fields must be strings.");
        if (value && (value->stringValue().find('\0') != std::string::npos ||
                      value->stringValue().size() > 65535)) {
            throw ContractError("Option text contains NUL or exceeds 65535 bytes.");
        }
    }
    for (const auto* name : {"array", "csv-format", "always-send", "never-send"}) {
        optionalField(object, name, Element::boolean, "Option flags must be booleans.");
    }
    optionalField(object, "user-context", Element::map, "user-context must be a map.");
    const auto classes = optionalField(object, "client-classes", Element::list,
                                       "client-classes must be a list of distinct strings.");
    if (classes) {
        std::set<std::string> unique;
        for (const auto& entry : classes->listValue()) {
            if (entry->getType() != Element::string || entry->stringValue().empty() ||
                entry->stringValue().find('\0') != std::string::npos ||
                !unique.insert(entry->stringValue()).second) {
                throw ContractError("client-classes must be a list of distinct nonempty strings.");
            }
        }
    }
}

template <typename Object> ElementPtr observedTags(const Object& object) {
    auto tags = Element::createList();
    for (const auto& tag : object.getServerTags()) {
        tags->add(Element::create(tag.get()));
    }
    return tags;
}

// Keep Kea's encoding engine, but exclude its process-global runtime fallback:
// that fallback may belong to a different selector or an older activation.
class SelectedOptionParser : public OptionDataParser {
  public:
    explicit SelectedOptionParser(const CfgOptionDefPtr& definitions)
        : OptionDataParser(AF_INET, definitions), definitions_(definitions) {}
    bool knows(const std::string& space, uint32_t code) const {
        return bool(findOptionDefinition(space, isc::util::Optional<uint32_t>(code),
                                         isc::util::Optional<std::string>()));
    }

  protected:
    OptionDefinitionPtr
    findOptionDefinition(const std::string& space, const isc::util::Optional<uint32_t>& code,
                         const isc::util::Optional<std::string>&) const override {
        auto definition = definitions_->get(space, code.get());
        if (!definition) {
            definition = LibDHCP::getOptionDef(space, code.get());
        }
        if (!definition) {
            const auto vendor = LibDHCP::optionSpaceToVendorId(space);
            if (vendor) {
                definition = LibDHCP::getVendorOptionDef(Option::V4, vendor, code.get());
            }
        }
        if (!definition) {
            definition = LibDHCP::getLastResortOptionDef(space, code.get());
        }
        return definition;
    }

  private:
    CfgOptionDefPtr definitions_;
};

int optionCommand(isc::hooks::CalloutHandle& handle, Operation operation, bool definitions) {
    return commandBoundary(
        handle,
        "Configuration backend operation failed; reconcile persisted state before retrying.",
        [&]() -> ConstElementPtr {
            const bool mutation = operation == Operation::Set || operation == Operation::Del;
            if (mutation) {
                requireMutationAdmission();
            }
            const auto arguments = commandRequest(handle).arguments;
            const char* object_name = definitions ? "option-def" : "option";
            const char* rows_name = definitions ? "option-defs" : "options";
            if (operation == Operation::List) {
                requireFields(arguments, {"server-tag"}, {}, "Expected only server-tag.");
            } else {
                requireFields(arguments, {"server-tag", object_name}, {},
                              "Expected only server-tag and one option-def or option map.");
            }
            const auto tag = optionTag(arguments);
            ConstElementPtr object;
            if (operation != Operation::List) {
                object = arguments->get(object_name);
                if (operation == Operation::Set && definitions) {
                    requireFields(object, {"name", "code", "space", "type"},
                                  {"array", "record-types", "encapsulate", "user-context"},
                                  "Invalid option definition fields.");
                } else if (operation == Operation::Set) {
                    requireFields(object, {"code", "space", "data"},
                                  {"name", "csv-format", "always-send", "never-send",
                                   "client-classes", "user-context"},
                                  "Invalid global option fields.");
                } else if (definitions) {
                    requireFields(object, {"code", "space"}, {}, "Expected only code and space.");
                } else {
                    requireFields(object, {"code", "space"}, {"client-classes"},
                                  "Expected code, space and optional client-classes.");
                }
                identity(object);
                typedFields(object);
            }
            const auto pool = backendPool<ConfigBackendDHCPv4Mgr>();
            const auto backend =
                singleBackendSelector(bool(pool), CfgMgr::instance().getCurrentCfg(),
                                      "Exactly one SQL configuration backend is required.",
                                      "Exactly one SQL configuration backend is required.",
                                      "A PostgreSQL or MySQL configuration backend is required.");
            if (!tag.amAll() && !pool->getServer4(backend, tag)) {
                throw ContractError("server-tag must already exist in the configuration backend.");
            }
            const auto selector = serverSelector(tag);
            const auto native_defs = pool->getAllOptionDefs4(backend, selector);
            CfgOptionDefPtr defs(new CfgOptionDef());
            for (const auto& def : native_defs) {
                defs->add(def);
            }
            const auto code = object ? object->get("code")->intValue() : 0;
            const auto space = object ? object->get("space")->stringValue() : std::string();
            const auto wanted_classes = object && object->get("client-classes")
                                            ? object->get("client-classes")
                                            : Element::createList();
            std::map<std::string, ElementPtr> sorted;
            auto observe = [&]() {
                sorted.clear();
                if (definitions) {
                    for (const auto& def : pool->getAllOptionDefs4(backend, selector)) {
                        if (object &&
                            (def->getCode() != code || def->getOptionSpaceName() != space)) {
                            continue;
                        }
                        CfgOptionDef one;
                        one.add(def);
                        auto row = Element::fromJSON(one.toElement()->get(0)->str());
                        row->set("server-tags", observedTags(*def));
                        const auto key =
                            def->getOptionSpaceName() + "/" + std::to_string(def->getCode());
                        if (!sorted.emplace(key, row).second) {
                            throw ContractError("Ambiguous option definition view.");
                        }
                    }
                } else {
                    for (const auto& desc : pool->getAllOptions4(backend, selector)) {
                        CfgOption options;
                        options.add(desc, desc.space_name_);
                        auto row = Element::fromJSON(options.toElement(defs)->get(0)->str());
                        if (!SelectedOptionParser(defs).knows(desc.space_name_,
                                                              desc.option_->getType())) {
                            row->remove("name"); // Never attribute a stale runtime definition.
                        }
                        const auto classes = row->get("client-classes") ? row->get("client-classes")
                                                                        : Element::createList();
                        if (object &&
                            (desc.option_->getType() != code || desc.space_name_ != space ||
                             !classes->equals(*wanted_classes))) {
                            continue;
                        }
                        row->set("server-tags", observedTags(desc));
                        const auto key = desc.space_name_ + "/" +
                                         std::to_string(desc.option_->getType()) + "/" +
                                         classes->str();
                        if (!sorted.emplace(key, row).second) {
                            throw ContractError("Ambiguous global option view.");
                        }
                    }
                }
            };
            observe();
            if (mutation && !sorted.empty()) {
                throw ContractError("Existing option mutations are unsupported: complete "
                                    "associations and dependencies cannot be verified.");
            }
            if (operation == Operation::Set) {
                if (definitions) {
                    OptionDefinitionPtr definition;
                    try {
                        auto input = Element::fromJSON(object->str());
                        if (!input->get("array"))
                            input->set("array", Element::create(false));
                        if (!input->get("record-types"))
                            input->set("record-types", Element::create(std::string()));
                        if (!input->get("encapsulate"))
                            input->set("encapsulate", Element::create(std::string()));
                        definition = OptionDefParser(AF_INET).parse(input);
                        defs->add(definition); // Reject duplicate names and builtin overrides.
                    } catch (...) {
                        throw ContractError("Invalid or conflicting native option definition.");
                    }
                    pool->createUpdateOptionDef4(backend, selector, definition);
                } else {
                    OptionDescriptorPtr descriptor;
                    try {
                        const SelectedOptionParser parser(defs);
                        const auto csv = object->get("csv-format");
                        if ((!csv || csv->boolValue()) && !parser.knows(space, code)) {
                            throw ContractError("CSV option data requires a selected definition.");
                        }
                        const auto parsed = SelectedOptionParser(defs).parse(object);
                        descriptor = OptionDescriptor::create(parsed.first);
                        descriptor->space_name_ = parsed.second;
                    } catch (...) {
                        throw ContractError("Invalid native option encoding or definition.");
                    }
                    pool->createUpdateOption4(backend, selector, descriptor);
                }
                observe();
                if (sorted.size() != 1) {
                    throw ContractError(
                        "Persisted option readback incomplete; reconcile before retrying.");
                }
            }
            auto rows = Element::createList();
            for (const auto& row : sorted) {
                rows->add(row.second);
            }
            auto result = Element::createMap();
            result->set("count", Element::create(static_cast<int64_t>(rows->size())));
            result->set(rows_name, rows);
            result->set("server-tag", Element::create(tag.get()));
            result->set("associations-complete", Element::create(false));
            if (mutation)
                result->set("activation-requested", Element::create(false));
            return createAnswer(rows->empty() ? CONTROL_RESULT_EMPTY : CONTROL_RESULT_SUCCESS,
                                "DHCPv4 option operation completed.", result);
        });
}
} // namespace

int optionDef4List(isc::hooks::CalloutHandle& h) {
    return optionCommand(h, Operation::List, true);
}
int optionDef4Get(isc::hooks::CalloutHandle& h) {
    return optionCommand(h, Operation::Get, true);
}
int optionDef4Set(isc::hooks::CalloutHandle& h) {
    return optionCommand(h, Operation::Set, true);
}
int optionDef4Del(isc::hooks::CalloutHandle& h) {
    return optionCommand(h, Operation::Del, true);
}
int optionGlobal4List(isc::hooks::CalloutHandle& h) {
    return optionCommand(h, Operation::List, false);
}
int optionGlobal4Get(isc::hooks::CalloutHandle& h) {
    return optionCommand(h, Operation::Get, false);
}
int optionGlobal4Set(isc::hooks::CalloutHandle& h) {
    return optionCommand(h, Operation::Set, false);
}
int optionGlobal4Del(isc::hooks::CalloutHandle& h) {
    return optionCommand(h, Operation::Del, false);
}
} // namespace kea_db_commands
