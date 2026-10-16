// SPDX-License-Identifier: MPL-2.0
#include <config.h>

#include "arguments.h"

#include <asiolink/addr_utilities.h>
#include <dhcpsrv/pool.h>

namespace kea_db_commands {

void validateLookupArguments(const isc::data::ConstElementPtr& arguments, const bool remove) {
    using namespace isc::data;
    using namespace isc::dhcp;
    if (!arguments || arguments->getType() != Element::map) {
        throw ContractError("Expected one id or subnet selector and optional server-tag.");
    }
    const auto id = arguments->get("id");
    const auto prefix = arguments->get("subnet");
    const auto tag_element = arguments->get("server-tag");
    const auto preserve = arguments->get("preserve-leases");
    if (remove && (!tag_element || !preserve || preserve->getType() != Element::boolean ||
                   !preserve->boolValue())) {
        throw ContractError("Deletion requires server-tag and preserve-leases: true.");
    }
    if (bool(id) == bool(prefix) ||
        arguments->mapValue().size() != (tag_element ? 2U : 1U) + (remove ? 1U : 0U)) {
        throw ContractError("Expected exactly one id or subnet selector and optional server-tag.");
    }
    if (id && (id->getType() != Element::integer || id->intValue() < 1 ||
               id->intValue() > SUBNET_ID_MAX)) {
        throw ContractError("id must be an integer in 1..4294967294.");
    }
    if (prefix) {
        try {
            if (prefix->getType() != Element::string) {
                throw ContractError("Invalid prefix type.");
            }
            const auto text = prefix->stringValue();
            const auto slash = text.find('/');
            if (slash == std::string::npos) {
                throw ContractError("Missing prefix length.");
            }
            const auto length_text = text.substr(slash + 1);
            if (length_text.empty() ||
                length_text.find_first_not_of("0123456789") != std::string::npos) {
                throw ContractError("Invalid prefix length.");
            }
            const auto length = std::stoul(length_text);
            const isc::asiolink::IOAddress address(text.substr(0, slash));
            if (!address.isV4() || length > 32 ||
                isc::asiolink::firstAddrInPrefix(address, length) != address ||
                text != address.toText() + "/" + std::to_string(length)) {
                throw ContractError("Noncanonical prefix.");
            }
        } catch (...) {
            throw ContractError("subnet must be a canonical IPv4 CIDR string.");
        }
    }
}

isc::dhcp::Subnet4Ptr parseSubnet4(const isc::data::ConstElementPtr& input) {
    using namespace isc::data;
    using namespace isc::dhcp;
    if (input->getType() != Element::map ||
        input->mapValue().size() != (input->get("pools") ? 4 : 3) || !input->get("id") ||
        !input->get("subnet") || !input->get("valid-lifetime")) {
        throw ContractError(
            "subnet4 requires id, subnet and valid-lifetime; only pools is optional.");
    }
    const auto id = input->get("id");
    const auto lifetime = input->get("valid-lifetime");
    if (id->getType() != Element::integer || id->intValue() < 1 || id->intValue() > SUBNET_ID_MAX ||
        lifetime->getType() != Element::integer || lifetime->intValue() < 1 ||
        lifetime->intValue() > 4294967294LL) {
        throw ContractError("id and valid-lifetime must be integers in 1..4294967294.");
    }
    const auto prefix = input->get("subnet");
    if (prefix->getType() != Element::string) {
        throw ContractError("subnet must be a canonical IPv4 CIDR string.");
    }
    Subnet4Ptr subnet;
    try {
        const auto text = prefix->stringValue();
        const auto slash = text.find('/');
        if (slash == std::string::npos) {
            throw ContractError("Missing prefix length.");
        }
        const auto length_text = text.substr(slash + 1);
        if (length_text.empty() ||
            length_text.find_first_not_of("0123456789") != std::string::npos) {
            throw ContractError("Invalid prefix length.");
        }
        const auto length = std::stoul(length_text);
        const isc::asiolink::IOAddress address(text.substr(0, slash));
        if (!address.isV4() || length > 32 ||
            isc::asiolink::firstAddrInPrefix(address, length) != address ||
            text != address.toText() + "/" + std::to_string(length)) {
            throw ContractError("Noncanonical prefix.");
        }
        subnet = Subnet4::create(address, length, 0, 0, lifetime->intValue(), id->intValue());
    } catch (...) {
        throw ContractError("subnet must be a canonical IPv4 CIDR string.");
    }
    const auto pools = input->get("pools");
    if (pools) {
        if (pools->getType() != Element::list) {
            throw ContractError("pools must be a list of start/end address maps.");
        }
        for (const auto& range : pools->listValue()) {
            if (range->getType() != Element::map || range->mapValue().size() != 2 ||
                !range->get("start") || !range->get("end") ||
                range->get("start")->getType() != Element::string ||
                range->get("end")->getType() != Element::string) {
                throw ContractError("Each pool supports only required start and end strings.");
            }
            try {
                const isc::asiolink::IOAddress first(range->get("start")->stringValue());
                const isc::asiolink::IOAddress last(range->get("end")->stringValue());
                // Kea 3.2.1 SQL readers treat a zero endpoint as an absent pool.
                if (first == isc::asiolink::IOAddress("0.0.0.0") ||
                    last == isc::asiolink::IOAddress("0.0.0.0")) {
                    throw ContractError("Zero pool endpoints cannot round-trip through Kea SQL.");
                }
                // Pool4 validates address family and ordering. addPool validates
                // subnet membership and overlap, including duplicate ranges.
                subnet->addPool(Pool4::create(first, last));
            } catch (...) {
                throw ContractError(
                    "Pools must be valid nonoverlapping IPv4 ranges within the subnet.");
            }
        }
    }
    return subnet;
}

} // namespace kea_db_commands
