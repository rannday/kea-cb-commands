// SPDX-License-Identifier: MPL-2.0
#include <config.h>

#include "backend_support.h"
#include "commands.h"

#include <cctype>
#include <cstdint>
#include <dhcpsrv/config_backend_dhcp4_mgr.h>
#include <map>

namespace kea_db_commands {
namespace {
using namespace isc::data;
using namespace isc::db;
using namespace isc::dhcp;
using namespace isc::config;
enum class Operation : std::uint8_t { List, Get, Set, Del };

std::string networkName(const ConstElementPtr& object) {
    const auto name = optionalField(object, "name", Element::string, "name must be a string.");
    if (!name || name->stringValue().empty() || name->stringValue().size() > 128 ||
        name->stringValue().find('\0') != std::string::npos ||
        std::isspace(static_cast<unsigned char>(name->stringValue().front())) ||
        std::isspace(static_cast<unsigned char>(name->stringValue().back()))) {
        throw ContractError(
            "name must be nonempty, at most 128 bytes, without NUL or surrounding whitespace.");
    }
    return name->stringValue();
}

SharedNetwork4Ptr newNetwork(const ConstElementPtr& object, const std::string& name) {
    auto network = SharedNetwork4::create(name);
    for (const auto* field : {"valid-lifetime", "renew-timer", "rebind-timer"}) {
        const auto value = optionalField(object, field, Element::integer,
                                         "Network timers must be integers in 1..2147483647.");
        if (!value) {
            continue;
        }
        if (value->intValue() < 1 || value->intValue() > 2147483647LL) {
            throw ContractError("Network timers must be integers in 1..2147483647.");
        }
        const isc::util::Triplet<uint32_t> timer(static_cast<uint32_t>(value->intValue()));
        if (std::string(field) == "valid-lifetime") {
            network->setValid(timer);
        } else if (std::string(field) == "renew-timer") {
            network->setT1(timer);
        } else {
            network->setT2(timer);
        }
    }
    const auto valid = object->get("valid-lifetime");
    const auto renew = object->get("renew-timer");
    const auto rebind = object->get("rebind-timer");
    if ((renew && rebind && renew->intValue() >= rebind->intValue()) ||
        (valid && renew && renew->intValue() >= valid->intValue()) ||
        (valid && rebind && rebind->intValue() >= valid->intValue())) {
        throw ContractError("Network timers must satisfy renew < rebind < valid when supplied.");
    }
    return network;
}

int networkCommand(isc::hooks::CalloutHandle& handle, Operation operation) {
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
                requireFields(arguments, {"server-tag", "shared-network"}, {},
                              "Expected only server-tag and one shared-network map.");
            } else {
                requireFields(arguments, {"server-tag", "name"}, {},
                              "Expected only server-tag and name.");
            }
            const auto field = optionalField(arguments, "server-tag", Element::string,
                                             "server-tag must be a string.");
            if (field->stringValue().find('\0') != std::string::npos) {
                throw ContractError("server-tag cannot contain NUL.");
            }
            const auto tag = validatedServerTag(field->stringValue());
            if (tag.get() == "any") {
                throw ContractError("The any selector is unsupported.");
            }
            std::string name;
            SharedNetwork4Ptr created;
            if (operation == Operation::Set) {
                const auto object = arguments->get("shared-network");
                requireFields(
                    object, {"name"}, {"valid-lifetime", "renew-timer", "rebind-timer"},
                    "Unsupported shared-network fields; membership and options are read-only.");
                name = networkName(object);
                created = newNetwork(object, name);
            } else if (operation != Operation::List) {
                name = networkName(arguments);
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
            // Network names are globally unique. ANY sees hidden/unassigned names.
            // This is a preflight, not a lock: exclusive writer ownership is required.
            if (mutation && pool->getSharedNetwork4(backend, ServerSelector::ANY(), name)) {
                throw ContractError("Existing shared-network mutations are unsupported: complete "
                                    "associations and dependencies cannot be verified.");
            }
            if (operation == Operation::Set) {
                pool->createUpdateSharedNetwork4(backend, selector, created);
            }
            std::map<std::string, SharedNetwork4Ptr> sorted;
            if (operation == Operation::List) {
                for (const auto& network : pool->getAllSharedNetworks4(backend, selector)) {
                    if (!sorted.emplace(network->getName(), network).second) {
                        throw ContractError("Ambiguous shared-network view.");
                    }
                }
            } else {
                const auto network = pool->getSharedNetwork4(backend, selector, name);
                if (network) {
                    sorted.emplace(name, network);
                }
            }
            if (operation == Operation::Set && sorted.size() != 1) {
                throw ContractError(
                    "Persisted network readback incomplete; reconcile before retrying.");
            }
            auto rows = Element::createList();
            for (const auto& entry : sorted) {
                auto row = Element::fromJSON(entry.second->toElement()->str());
                auto tags = Element::createList();
                for (const auto& observed : entry.second->getServerTags()) {
                    tags->add(Element::create(observed.get()));
                }
                row->set("server-tags", tags);
                // Both pinned SQL drivers use ANY regardless of the passed selector.
                // Preserve that evidence explicitly; never relabel it as selected.
                std::map<SubnetID, Subnet4Ptr> members;
                for (const auto& subnet :
                     pool->getSharedNetworkSubnets4(backend, ServerSelector::ANY(), entry.first)) {
                    if (!members.emplace(subnet->getID(), subnet).second) {
                        throw ContractError("Ambiguous shared-network membership.");
                    }
                }
                auto subnets = Element::createList();
                for (const auto& member : members) {
                    auto subnet = Element::fromJSON(member.second->toElement()->str());
                    auto associations = Element::createList();
                    for (const auto& observed : member.second->getServerTags()) {
                        associations->add(Element::create(observed.get()));
                    }
                    subnet->set("server-tags", associations);
                    subnets->add(subnet);
                }
                row->set("subnet4", subnets);
                rows->add(row);
            }
            auto result = Element::createMap();
            result->set("count", Element::create(static_cast<int64_t>(rows->size())));
            result->set("shared-networks", rows);
            result->set("server-tag", Element::create(tag.get()));
            result->set("associations-complete", Element::create(false));
            result->set("membership-selector", Element::create(std::string("ANY")));
            if (mutation) {
                result->set("activation-requested", Element::create(false));
            }
            return createAnswer(rows->empty() ? CONTROL_RESULT_EMPTY : CONTROL_RESULT_SUCCESS,
                                "DHCPv4 shared-network operation completed.", result);
        });
}
} // namespace
int sharedNetwork4List(isc::hooks::CalloutHandle& h) {
    return networkCommand(h, Operation::List);
}
int sharedNetwork4Get(isc::hooks::CalloutHandle& h) {
    return networkCommand(h, Operation::Get);
}
int sharedNetwork4Set(isc::hooks::CalloutHandle& h) {
    return networkCommand(h, Operation::Set);
}
int sharedNetwork4Del(isc::hooks::CalloutHandle& h) {
    return networkCommand(h, Operation::Del);
}
} // namespace kea_db_commands
