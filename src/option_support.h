// SPDX-License-Identifier: MPL-2.0
#ifndef KEA_DB_COMMANDS_OPTION_SUPPORT_H
#define KEA_DB_COMMANDS_OPTION_SUPPORT_H

#include "backend_support.h"

#include <dhcp/libdhcp++.h>
#include <dhcp/option_space.h>
#include <dhcpsrv/cfg_option_def.h>
#include <dhcpsrv/parsers/option_data_parser.h>
#include <set>
#include <sys/socket.h>

namespace kea_db_commands {
namespace option_support {
using namespace isc::data;
using namespace isc::db;
using namespace isc::dhcp;
inline ServerTag optionTag(const ConstElementPtr& arguments) {
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

inline void identity(const ConstElementPtr& object) {
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

inline void typedFields(const ConstElementPtr& object) {
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

inline OptionDescriptorPtr parseOption(const ConstElementPtr& object,
                                       const CfgOptionDefPtr& definitions) {
    try {
        SelectedOptionParser parser(definitions);
        const auto csv = object->get("csv-format");
        if ((!csv || csv->boolValue()) &&
            !parser.knows(object->get("space")->stringValue(), object->get("code")->intValue())) {
            throw ContractError("CSV option data requires a selected definition.");
        }
        const auto parsed = parser.parse(object);
        auto descriptor = OptionDescriptor::create(parsed.first);
        descriptor->space_name_ = parsed.second;
        return descriptor;
    } catch (...) {
        throw ContractError("Invalid native option encoding or definition.");
    }
}
} // namespace option_support
} // namespace kea_db_commands
#endif
