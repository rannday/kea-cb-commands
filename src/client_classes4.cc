// SPDX-License-Identifier: MPL-2.0
#include <config.h>

#include "commands.h"
#include "option_support.h"

#include <cctype>
#include <cstdint>
#include <dhcpsrv/config_backend_dhcp4_mgr.h>
#include <dhcpsrv/parsers/client_class_def_parser.h>
#include <set>

namespace kea_db_commands {
namespace {
using namespace isc::data;
using namespace isc::db;
using namespace isc::dhcp;
using namespace isc::config;
using namespace option_support;
enum class Operation : std::uint8_t { List, Get, Set, Del };

bool containsName(const ConstElementPtr& value, const std::string& name) {
    if (!value)
        return false;
    if (value->getType() == Element::string)
        return value->stringValue() == name;
    if (value->getType() == Element::list) {
        for (const auto& item : value->listValue())
            if (containsName(item, name))
                return true;
    }
    return false;
}

// Dormant textual consumers must not acquire new meaning through a fresh class.
// Inspect native serialized objects without changing or activating any of them.
void rejectReferences(const ConstElementPtr& value, const std::string& name) {
    if (!value)
        return;
    if (value->getType() == Element::map) {
        for (const auto& entry : value->mapValue()) {
            if ((entry.first == "client-class" || entry.first == "client-classes" ||
                 entry.first == "evaluate-additional-classes" ||
                 entry.first == "require-client-classes") &&
                containsName(entry.second, name)) {
                throw ContractError(
                    "Fresh class has an existing textual consumer; creation refused.");
            }
            if (entry.first == "test" && entry.second->getType() == Element::string &&
                !entry.second->stringValue().empty()) {
                bool referenced = false;
                ExpressionPtr expression;
                ExpressionParser().parse(expression, entry.second, AF_INET,
                                         [&](const ClientClass& dependency) {
                                             referenced = referenced || dependency == name;
                                             return true;
                                         });
                if (referenced)
                    throw ContractError(
                        "Fresh class has an existing expression consumer; creation refused.");
            }
            rejectReferences(entry.second, name);
        }
    } else if (value->getType() == Element::list) {
        for (const auto& item : value->listValue())
            rejectReferences(item, name);
    }
}

void requireFreshConsumers(const boost::shared_ptr<ConfigBackendPoolDHCPv4>& pool,
                           const BackendSelector& backend, const std::string& name) {
    rejectReferences(CfgMgr::instance().getCurrentCfg()->toElement(), name);
    const auto inspect = [&](const ServerSelector& selector) {
        for (const auto& subnet : pool->getAllSubnets4(backend, selector))
            rejectReferences(subnet->toElement(), name);
        for (const auto& network : pool->getAllSharedNetworks4(backend, selector))
            rejectReferences(network->toElement(), name);
        for (const auto& option : pool->getAllOptions4(backend, selector))
            for (const auto& dependency : option.client_classes_)
                if (dependency == name)
                    throw ContractError(
                        "Fresh class has an existing option consumer; creation refused.");
    };
    inspect(ServerSelector::ALL());
    inspect(ServerSelector::UNASSIGNED());
    for (const auto& server : pool->getAllServers4(backend))
        inspect(ServerSelector::ONE(server->getServerTagAsText()));
    for (const auto& selector : {ServerSelector::ANY(), ServerSelector::UNASSIGNED()}) {
        const auto classes = pool->getAllClientClasses4(backend, selector);
        for (const auto& definition : *classes.getClasses())
            rejectReferences(definition->toElement(), name);
    }
}

std::string className(const ConstElementPtr& object) {
    const auto value = optionalField(object, "name", Element::string, "name must be a string.");
    if (!value || value->stringValue().empty() || value->stringValue().size() > 128 ||
        value->stringValue().find('\0') != std::string::npos ||
        std::isspace(static_cast<unsigned char>(value->stringValue().front())) ||
        std::isspace(static_cast<unsigned char>(value->stringValue().back()))) {
        throw ContractError(
            "name must be nonempty, at most 128 bytes, without NUL or surrounding whitespace.");
    }
    return value->stringValue();
}

ElementPtr dependencies(const ClientClassDefPtr& definition) {
    auto result = Element::createList();
    if (!definition->getTest().empty()) {
        std::set<std::string> seen;
        ExpressionPtr expression;
        ExpressionParser().parse(expression, Element::create(definition->getTest()), AF_INET,
                                 [&](const ClientClass& name) {
                                     if (seen.insert(name).second) {
                                         result->add(Element::create(name));
                                     }
                                     return true;
                                 });
    }
    return result;
}

int classCommand(isc::hooks::CalloutHandle& handle, Operation operation) {
    return commandBoundary(
        handle,
        "Configuration backend operation failed; reconcile persisted state before retrying.",
        [&]() -> ConstElementPtr {
            const bool mutation = operation == Operation::Set || operation == Operation::Del;
            if (mutation) {
                requireMutationAdmission();
            }
            const auto arguments = commandRequest(handle).arguments;
            if (operation == Operation::List) {
                requireFields(arguments, {"server-tag"}, {}, "Expected only server-tag.");
            } else if (operation == Operation::Set) {
                requireFields(
                    arguments, {"server-tag", "client-class", "follow-class-name"}, {},
                    "Expected server-tag, one client-class map and explicit follow-class-name.");
            } else {
                requireFields(arguments, {"server-tag", "name"}, {},
                              "Expected only server-tag and name.");
            }
            const auto tag = optionTag(arguments);
            const auto selector = serverSelector(tag);
            const auto pool = backendPool<ConfigBackendDHCPv4Mgr>();
            const auto backend =
                singleBackendSelector(bool(pool), CfgMgr::instance().getCurrentCfg(),
                                      "Exactly one SQL configuration backend is required.",
                                      "Exactly one SQL configuration backend is required.",
                                      "A PostgreSQL or MySQL configuration backend is required.");
            if (!tag.amAll() && !pool->getServer4(backend, tag)) {
                throw ContractError("server-tag must already exist in the configuration backend.");
            }
            std::string name;
            ConstElementPtr object;
            if (operation == Operation::Set) {
                object = arguments->get("client-class");
                requireFields(object, {"name"},
                              {"test", "only-in-additional-list", "option-data", "next-server",
                               "server-hostname", "boot-file-name", "valid-lifetime",
                               "min-valid-lifetime", "max-valid-lifetime", "user-context"},
                              "Unsupported client-class fields.");
                name = className(object);
            } else if (operation != Operation::List) {
                name = className(arguments);
            }
            // A class name is globally unique, even when hidden from this selector.
            // No native existing-object write/delete is safe with incomplete consumers.
            if (mutation && (pool->getClientClass4(backend, ServerSelector::ANY(), name) ||
                             pool->getAllClientClasses4(backend, ServerSelector::UNASSIGNED())
                                 .findClass(name))) {
                throw ContractError("Existing client-class mutations are unsupported: complete "
                                    "associations and dependencies cannot be verified.");
            }
            ClientClassDictionaryPtr dictionary(
                new ClientClassDictionary(pool->getAllClientClasses4(backend, selector)));
            if (operation == Operation::Set) {
                const auto follow = optionalField(
                    arguments, "follow-class-name", Element::string,
                    "follow-class-name must be an explicit string; empty means append.");
                if (!follow || !follow->stringValue().empty()) {
                    throw ContractError("Only explicit append (follow-class-name: empty string) is "
                                        "supported; insertion and reordering are refused.");
                }
                if (isClientClassBuiltIn(name) || name == "DROP" || name == "REJECT" ||
                    name.compare(0, 6, "SPAWN_") == 0) {
                    throw ContractError(
                        "Built-in, special and generated class names cannot be created.");
                }
                requireFreshConsumers(pool, backend, name);
                auto input = Element::fromJSON(object->str());
                const auto options = input->get("option-data");
                input->remove("option-data");
                for (const auto* field :
                     {"test", "next-server", "server-hostname", "boot-file-name"}) {
                    const auto value = optionalField(input, field, Element::string,
                                                     "Class text fields must be strings.");
                    if (value && (value->stringValue().find('\0') != std::string::npos ||
                                  value->stringValue().size() > 65535)) {
                        throw ContractError("Class text contains NUL or exceeds 65535 bytes.");
                    }
                }
                for (const auto* field :
                     {"valid-lifetime", "min-valid-lifetime", "max-valid-lifetime"}) {
                    const auto value =
                        optionalField(input, field, Element::integer,
                                      "Class lifetimes must be integers in 1..2147483647.");
                    if (value && (value->intValue() < 1 || value->intValue() > 2147483647LL)) {
                        throw ContractError("Class lifetimes must be integers in 1..2147483647.");
                    }
                }
                if ((input->get("min-valid-lifetime") || input->get("max-valid-lifetime")) &&
                    !input->get("valid-lifetime")) {
                    throw ContractError("Lifetime bounds require valid-lifetime.");
                }
                ClientClassDefPtr created;
                try {
                    ClientClassDefParser().parse(dictionary, input, AF_INET, false, true);
                    created = dictionary->findClass(name);
                } catch (...) {
                    throw ContractError(
                        "Invalid native client-class definition, expression or dependency.");
                }
                if (options) {
                    if (options->getType() != Element::list) {
                        throw ContractError("option-data must be a list.");
                    }
                    CfgOptionDefPtr definitions(new CfgOptionDef());
                    for (const auto& definition : pool->getAllOptionDefs4(backend, selector)) {
                        definitions->add(definition);
                    }
                    std::set<std::pair<std::string, int64_t>> identities;
                    for (const auto& option : options->listValue()) {
                        requireFields(option, {"code", "space", "data"},
                                      {"csv-format", "always-send", "never-send", "user-context"},
                                      "Unsupported class option fields; class guards and nested "
                                      "definitions are unsupported.");
                        identity(option);
                        typedFields(option);
                        const auto space = option->get("space")->stringValue();
                        if (!identities.emplace(space, option->get("code")->intValue()).second) {
                            throw ContractError("Duplicate class option identity.");
                        }
                        const auto parsed = parseOption(option, definitions);
                        created->getCfgOption()->add(*parsed, space);
                    }
                }
                // Empty predecessor has the pinned native append semantics. All validation
                // precedes this sole write. Exclusive writer ownership remains mandatory.
                pool->createUpdateClientClass4(backend, selector, created, "");
                dictionary.reset(
                    new ClientClassDictionary(pool->getAllClientClasses4(backend, selector)));
                if (!dictionary->findClass(name)) {
                    throw ContractError(
                        "Persisted class readback incomplete; reconcile before retrying.");
                }
            }
            auto rows = Element::createList();
            int64_t position = 0;
            for (const auto& definition : *dictionary->getClasses()) {
                const auto index = position++;
                if (operation != Operation::List && definition->getName() != name) {
                    continue;
                }
                auto row = Element::fromJSON(definition->toElement()->str());
                row->set("server-tags", observedTags(*definition));
                row->set("modification-ts",
                         Element::create(boost::posix_time::to_iso_extended_string(
                             definition->getModificationTime())));
                row->set("evaluation-position", Element::create(index));
                row->set("referenced-classes", dependencies(definition));
                row->set("depend-on-known", Element::create(definition->getDependOnKnown()));
                rows->add(row);
            }
            auto result = Element::createMap();
            result->set("client-classes", rows);
            result->set("count", Element::create(static_cast<int64_t>(rows->size())));
            result->set("server-tag", Element::create(tag.get()));
            result->set("order-scope", Element::create(std::string("selected-view")));
            result->set("associations-complete", Element::create(false));
            result->set("dependencies-complete", Element::create(false));
            if (mutation) {
                result->set("activation-requested", Element::create(false));
            }
            return createAnswer(rows->empty() ? CONTROL_RESULT_EMPTY : CONTROL_RESULT_SUCCESS,
                                "DHCPv4 client-class operation completed.", result);
        });
}
} // namespace
int clientClass4List(isc::hooks::CalloutHandle& h) {
    return classCommand(h, Operation::List);
}
int clientClass4Get(isc::hooks::CalloutHandle& h) {
    return classCommand(h, Operation::Get);
}
int clientClass4Set(isc::hooks::CalloutHandle& h) {
    return classCommand(h, Operation::Set);
}
int clientClass4Del(isc::hooks::CalloutHandle& h) {
    return classCommand(h, Operation::Del);
}
} // namespace kea_db_commands
