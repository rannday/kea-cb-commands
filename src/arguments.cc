// SPDX-License-Identifier: MPL-2.0
#include <config.h>

#include "arguments.h"
#include "command_support.h"

#include <asiolink/addr_utilities.h>
#include <dhcpsrv/pool.h>
#include <set>

namespace kea_db_commands {
namespace {

const char* const subnet4_attributes[] = {"renew-timer",
                                          "rebind-timer",
                                          "next-server",
                                          "server-hostname",
                                          "boot-file-name",
                                          "client-classes",
                                          "evaluate-additional-classes"};

template <typename Object>
void applyClasses(const isc::data::ConstElementPtr& input, const Object& object) {
    using namespace isc::data;
    for (const auto* name : {"client-classes", "evaluate-additional-classes"}) {
        const auto classes = optionalField(input, name, Element::list,
                                           "Class restrictions must be lists of strings.");
        if (!classes) {
            continue;
        }
        std::set<std::string> seen;
        for (const auto& value : classes->listValue()) {
            if (value->getType() != Element::string || value->stringValue().empty() ||
                value->stringValue().find('\0') != std::string::npos ||
                !seen.insert(value->stringValue()).second) {
                throw ContractError("Class names must be distinct nonempty strings without NUL.");
            }
            if (std::string(name) == "client-classes") {
                object->allowClientClass(value->stringValue());
            } else {
                object->addAdditionalClass(value->stringValue());
            }
        }
    }
}

void applySubnet4Attributes(const isc::data::ConstElementPtr& input,
                            const isc::dhcp::Subnet4Ptr& subnet) {
    using namespace isc::data;
    for (const auto* name : {"renew-timer", "rebind-timer"}) {
        const auto timer = optionalField(input, name, Element::integer,
                                         "Timers must be integers in 0..2147483647.");
        if (timer) {
            if (timer->intValue() < 0 || timer->intValue() > 2147483647LL) {
                throw ContractError("Timers must be integers in 0..2147483647.");
            }
            if (std::string(name) == "renew-timer") {
                subnet->setT1(isc::util::Triplet<uint32_t>(timer->intValue()));
            } else {
                subnet->setT2(isc::util::Triplet<uint32_t>(timer->intValue()));
            }
        }
    }
    const auto t1 = subnet->getT1(isc::dhcp::Network::Inheritance::NONE).get();
    const auto t2 = subnet->getT2(isc::dhcp::Network::Inheritance::NONE).get();
    const auto valid = subnet->getValid(isc::dhcp::Network::Inheritance::NONE).get();
    if ((t1 && t1 >= valid) || (t2 && t2 >= valid) || (t1 && t2 && t1 > t2)) {
        throw ContractError("Nonzero timers require renew <= rebind and each < valid-lifetime.");
    }
    const auto next = optionalField(input, "next-server", Element::string,
                                    "next-server must be an IPv4 address.");
    if (next) {
        try {
            const isc::asiolink::IOAddress address(next->stringValue());
            subnet->setSiaddr(isc::util::Optional<isc::asiolink::IOAddress>(address));
        } catch (...) {
            throw ContractError("next-server must be an IPv4 address.");
        }
    }
    for (const auto* name : {"server-hostname", "boot-file-name"}) {
        const auto value =
            optionalField(input, name, Element::string, "Boot parameters must be strings.");
        if (!value) {
            continue;
        }
        if (value->stringValue().find('\0') != std::string::npos) {
            throw ContractError("Boot parameters must not contain NUL.");
        }
        const auto limit = std::string(name) == "server-hostname" ? 63U : 127U;
        if (value->stringValue().size() > limit) {
            throw ContractError("server-hostname is limited to 63 bytes; boot-file-name to 127.");
        }
        try {
            if (std::string(name) == "server-hostname") {
                subnet->setSname(isc::util::Optional<std::string>(value->stringValue()));
            } else {
                subnet->setFilename(isc::util::Optional<std::string>(value->stringValue()));
            }
        } catch (...) {
            throw ContractError("server-hostname is limited to 63 bytes; boot-file-name to 127.");
        }
    }
    applyClasses(input, subnet);
}

} // namespace

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
    requireFields(input, {"id", "subnet", "valid-lifetime"},
                  {"pools", "renew-timer", "rebind-timer", "next-server", "server-hostname",
                   "boot-file-name", "client-classes", "evaluate-additional-classes"},
                  "subnet4 requires id, subnet and valid-lifetime; only pools is optional.");
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
    applySubnet4Attributes(input, subnet);
    const auto pools = optionalField(input, "pools", Element::list,
                                     "pools must be a list of start/end address maps.");
    if (pools) {
        for (const auto& range : pools->listValue()) {
            requireFields(range, {},
                          {"start", "end", "pool", "client-classes", "evaluate-additional-classes"},
                          "Unsupported pool field.");
            const auto notation = optionalField(range, "pool", Element::string,
                                                "pool must be a canonical IPv4 CIDR string.");
            const auto start = optionalField(range, "start", Element::string,
                                             "start must be an IPv4 address string.");
            const auto end =
                optionalField(range, "end", Element::string, "end must be an IPv4 address string.");
            if (notation ? bool(start || end) : !start || !end) {
                throw ContractError("Each pool supports only required start and end strings.");
            }
            try {
                auto first = isc::asiolink::IOAddress("0.0.0.0");
                auto last = first;
                if (notation) {
                    // Reuse the canonical subnet identity validator, not a second
                    // permissive prefix parser.
                    auto identity = Element::createMap();
                    identity->set("subnet", notation);
                    validateLookupArguments(identity, false);
                    const auto text = notation->stringValue();
                    const auto slash = text.find('/');
                    const auto length = std::stoul(text.substr(slash + 1));
                    first = isc::asiolink::IOAddress(text.substr(0, slash));
                    last = isc::asiolink::lastAddrInPrefix(first, length);
                } else {
                    first = isc::asiolink::IOAddress(start->stringValue());
                    last = isc::asiolink::IOAddress(end->stringValue());
                }
                // Kea 3.2.1 SQL readers treat a zero endpoint as an absent pool.
                if (first == isc::asiolink::IOAddress("0.0.0.0") ||
                    last == isc::asiolink::IOAddress("0.0.0.0")) {
                    throw ContractError("Zero pool endpoints cannot round-trip through Kea SQL.");
                }
                // Pool4 validates address family and ordering. addPool validates
                // subnet membership and overlap, including duplicate ranges.
                const auto pool = Pool4::create(first, last);
                applyClasses(range, pool);
                subnet->addPool(pool);
            } catch (...) {
                throw ContractError(
                    "Pools must be valid nonoverlapping IPv4 ranges within the subnet.");
            }
        }
    }
    return subnet;
}

isc::dhcp::Subnet4Ptr preserveSubnet4(const isc::data::ConstElementPtr& input,
                                      const isc::dhcp::Subnet4Ptr& existing) {
    using namespace isc::data;
    using namespace isc::dhcp;
    if (!existing->getSharedNetworkName().empty()) {
        throw ContractError("Existing subnet contains unsupported configuration; update refused.");
    }
    const auto stored = existing->toElement();
    auto preserved = Element::createMap();
    for (const auto* name : {"id", "subnet", "valid-lifetime"}) {
        preserved->set(name, stored->get(name));
    }
    for (const auto* name : subnet4_attributes) {
        if (stored->contains(name)) {
            preserved->set(name, stored->get(name));
        }
    }
    auto pools = Element::createList();
    bool restricted_pool = false;
    for (const auto& pool : existing->getPools(Lease::TYPE_V4)) {
        auto range = Element::createMap();
        range->set("start", Element::create(pool->getFirstAddress().toText()));
        range->set("end", Element::create(pool->getLastAddress().toText()));
        const auto fields = pool->toElement();
        for (const auto* name : {"client-classes", "evaluate-additional-classes"}) {
            if (fields->contains(name)) {
                range->set(name, fields->get(name));
                restricted_pool = restricted_pool || !fields->get(name)->listValue().empty();
            }
        }
        pools->add(range);
    }
    preserved->set("pools", pools);
    // Validate the entire native representation against the bounded model.
    // Options, context, membership and nontrivial lifetime bounds are not
    // reconstructed: any such difference refuses the whole-object write.
    if (!stored->equals(*parseSubnet4(preserved)->toElement())) {
        throw ContractError("Existing subnet contains unsupported configuration; update refused.");
    }
    if (input->contains("pools") && restricted_pool) {
        throw ContractError("Replacing pools with existing class restrictions is unsupported.");
    }
    auto merged = Element::createMap();
    for (const auto* name : {"id", "subnet", "valid-lifetime"}) {
        merged->set(name, input->get(name));
    }
    for (const auto* name : subnet4_attributes) {
        const auto value = input->contains(name) ? input->get(name) : preserved->get(name);
        if (value) {
            merged->set(name, value);
        }
    }
    merged->set("pools", input->contains("pools") ? input->get("pools") : pools);
    return parseSubnet4(merged);
}

} // namespace kea_db_commands
