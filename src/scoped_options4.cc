// SPDX-License-Identifier: MPL-2.0
#include <config.h>

#include "option_support.h"

#include <dhcpsrv/config_backend_dhcp4_mgr.h>
#include <map>

namespace kea_db_commands {
namespace {
using namespace isc::data;
using namespace isc::db;
using namespace isc::dhcp;
using namespace isc::config;
using namespace option_support;
enum class Scope { Network, Subnet, Pool };
enum class Operation { List, Get, Set, Del };

// Range-only native writes have no subnet key. Cover every association partition,
// including unassigned subnets; deduplicate IDs before examining physical pools.
void requireUniqueRange(const boost::shared_ptr<ConfigBackendPoolDHCPv4>& backend_pool,
                        const BackendSelector& backend, const isc::asiolink::IOAddress& first,
                        const isc::asiolink::IOAddress& last) {
    std::set<SubnetID> ids;
    const auto collect = [&](const ServerSelector& selector) {
        for (const auto& subnet : backend_pool->getAllSubnets4(backend, selector))
            ids.insert(subnet->getID());
    };
    collect(ServerSelector::ALL());
    collect(ServerSelector::UNASSIGNED());
    for (const auto& server : backend_pool->getAllServers4(backend))
        collect(ServerSelector::ONE(server->getServerTagAsText()));
    unsigned matches = 0;
    for (const auto id : ids) {
        const auto subnet = backend_pool->getSubnet4(backend, ServerSelector::ANY(), id);
        if (!subnet)
            throw ContractError("Incomplete pool identity evidence.");
        for (const auto& pool : subnet->getPools(Lease::TYPE_V4))
            if (pool->getFirstAddress() == first && pool->getLastAddress() == last)
                ++matches;
    }
    if (matches != 1)
        throw ContractError("Pool range is not globally unique; scoped mutation refused.");
}

int scopedOptionCommand(isc::hooks::CalloutHandle& handle, Scope scope, Operation operation) {
    return commandBoundary(
        handle,
        "Configuration backend operation failed; reconcile persisted state before retrying.",
        [&]() -> ConstElementPtr {
            const bool mutation = operation == Operation::Set || operation == Operation::Del;
            if (mutation)
                requireMutationAdmission();
            const auto arguments = commandRequest(handle).arguments;
            requireFields(arguments, {"server-tag", "parent"},
                          operation == Operation::List
                              ? std::initializer_list<const char*>{}
                              : std::initializer_list<const char*>{"option"},
                          "Expected server-tag, parent and an option for non-list operations.");
            const auto tag = optionTag(arguments);
            const auto parent = arguments->get("parent");
            SubnetID subnet_id = 0;
            std::string network_name;
            isc::asiolink::IOAddress first("0.0.0.0"), last("0.0.0.0");
            if (scope == Scope::Network) {
                requireFields(parent, {"shared-network-name"}, {}, "Expected shared-network-name.");
                const auto name = optionalField(parent, "shared-network-name", Element::string,
                                                "shared-network-name must be a string.");
                network_name = name->stringValue();
                if (network_name.empty() || network_name.size() > 128 ||
                    network_name.find('\0') != std::string::npos ||
                    network_name.find_first_of(" \t\r\n") == 0 ||
                    network_name.find_last_of(" \t\r\n") == network_name.size() - 1)
                    throw ContractError("Invalid shared-network-name.");
            } else {
                requireFields(parent, {"subnet-id"},
                              scope == Scope::Pool
                                  ? std::initializer_list<const char*>{"start", "end"}
                                  : std::initializer_list<const char*>{},
                              "Expected subnet-id and, for pools, start and end.");
                const auto id = optionalField(parent, "subnet-id", Element::integer,
                                              "subnet-id must be an integer in 1..4294967294.");
                if (id->intValue() < 1 || id->intValue() > 4294967294LL)
                    throw ContractError("subnet-id must be an integer in 1..4294967294.");
                subnet_id = static_cast<SubnetID>(id->intValue());
                if (scope == Scope::Pool) {
                    const auto start = optionalField(parent, "start", Element::string,
                                                     "Pool start and end must be IPv4 strings.");
                    const auto end = optionalField(parent, "end", Element::string,
                                                   "Pool start and end must be IPv4 strings.");
                    if (!start || !end)
                        throw ContractError("Pool start and end are required.");
                    try {
                        first = isc::asiolink::IOAddress(start->stringValue());
                        last = isc::asiolink::IOAddress(end->stringValue());
                        if (!first.isV4() || !last.isV4() || last < first ||
                            first.toText() != start->stringValue() ||
                            last.toText() != end->stringValue())
                            throw ContractError("Invalid pool range.");
                    } catch (...) {
                        throw ContractError("Invalid canonical IPv4 pool range.");
                    }
                }
            }
            const auto object = arguments->get("option");
            if (operation == Operation::List) {
                if (object)
                    throw ContractError("List does not accept option.");
            } else {
                if (operation == Operation::Set)
                    requireFields(object, {"code", "space", "data"},
                                  {"name", "csv-format", "always-send", "never-send",
                                   "client-classes", "user-context"},
                                  "Invalid scoped option fields.");
                else
                    requireFields(object, {"code", "space"}, {"client-classes"},
                                  "Expected code, space and optional client-classes.");
                identity(object);
                typedFields(object);
            }
            const auto pool = backendPool<ConfigBackendDHCPv4Mgr>();
            const auto backend =
                singleBackendSelector(bool(pool), CfgMgr::instance().getCurrentCfg(),
                                      "Exactly one SQL configuration backend is required.",
                                      "Exactly one SQL configuration backend is required.",
                                      "A PostgreSQL or MySQL configuration backend is required.");
            if (!tag.amAll() && !pool->getServer4(backend, tag))
                throw ContractError("server-tag must already exist in the configuration backend.");
            const auto selector = mutation ? ServerSelector::ANY() : serverSelector(tag);
            CfgOptionPtr options;
            ElementPtr parent_tags;
            const auto observeParent = [&]() {
                if (scope == Scope::Network) {
                    const auto network = pool->getSharedNetwork4(backend, selector, network_name);
                    if (!network)
                        throw ContractError("Shared-network parent not found in selector view.");
                    parent_tags = observedTags(*network);
                    options = network->getCfgOption();
                } else {
                    const auto subnet = pool->getSubnet4(backend, selector, subnet_id);
                    if (!subnet)
                        throw ContractError("Subnet parent not found in selector view.");
                    parent_tags = observedTags(*subnet);
                    options = subnet->getCfgOption();
                    if (scope == Scope::Pool) {
                        options.reset();
                        for (const auto& candidate : subnet->getPools(Lease::TYPE_V4))
                            if (candidate->getFirstAddress() == first &&
                                candidate->getLastAddress() == last) {
                                if (options)
                                    throw ContractError("Ambiguous pool parent.");
                                options = candidate->getCfgOption();
                            }
                        if (!options)
                            throw ContractError("Pool parent not found in subnet.");
                    }
                }
            };
            observeParent();
            if (mutation &&
                (parent_tags->size() != 1 || parent_tags->get(0)->stringValue() != tag.get()))
                throw ContractError(
                    "Scoped mutation requires exactly the requested parent association.");
            CfgOptionDefPtr definitions(new CfgOptionDef());
            for (const auto& def : pool->getAllOptionDefs4(backend, serverSelector(tag)))
                definitions->add(def);
            const auto code = object ? object->get("code")->intValue() : 0;
            const auto space = object ? object->get("space")->stringValue() : std::string();
            const auto classes = object && object->get("client-classes")
                                     ? object->get("client-classes")
                                     : Element::createList();
            bool any_matching_identity = false;
            auto rows = Element::createList();
            const auto observeOptions = [&]() {
                rows = Element::createList();
                any_matching_identity = false;
                std::map<std::string, ElementPtr> sorted;
                for (const auto& option_space : options->getOptionSpaceNames()) {
                    for (const auto& descriptor : *options->getAll(option_space)) {
                        CfgOption one;
                        one.add(descriptor, option_space);
                        auto row = Element::fromJSON(one.toElement(definitions)->get(0)->str());
                        if (!SelectedOptionParser(definitions)
                                 .knows(option_space, descriptor.option_->getType()))
                            row->remove("name");
                        const auto actual_classes = row->get("client-classes")
                                                        ? row->get("client-classes")
                                                        : Element::createList();
                        const bool matches = object && descriptor.option_->getType() == code &&
                                             option_space == space;
                        any_matching_identity = any_matching_identity || matches;
                        if (object && (!matches || !actual_classes->equals(*classes)))
                            continue;
                        const auto key = option_space + "/" +
                                         std::to_string(descriptor.option_->getType()) + "/" +
                                         actual_classes->str();
                        if (!sorted.emplace(key, row).second)
                            throw ContractError("Ambiguous scoped option view.");
                    }
                }
                for (const auto& row : sorted)
                    rows->add(row.second);
            };
            observeOptions();
            if (mutation && any_matching_identity)
                throw ContractError("Existing scoped option mutations are unsupported: complete "
                                    "associations and dependencies cannot be verified.");
            if (operation == Operation::Set) {
                const auto descriptor = parseOption(object, definitions);
                if (scope == Scope::Pool) {
                    requireUniqueRange(pool, backend, first, last);
                    pool->createUpdateOption4(backend, ServerSelector::ANY(), first, last,
                                              descriptor);
                } else if (scope == Scope::Network) {
                    pool->createUpdateOption4(backend, ServerSelector::ANY(), network_name,
                                              descriptor);
                } else {
                    pool->createUpdateOption4(backend, ServerSelector::ANY(), subnet_id,
                                              descriptor);
                }
                observeParent();
                observeOptions();
                if (rows->size() != 1)
                    throw ContractError(
                        "Persisted scoped option readback incomplete; reconcile before retrying.");
            }
            auto result = Element::createMap();
            result->set("count", Element::create(static_cast<int64_t>(rows->size())));
            result->set("options", rows);
            result->set("parent", parent);
            result->set("server-tag", Element::create(tag.get()));
            result->set("parent-server-tags", parent_tags);
            result->set("associations-complete", Element::create(false));
            if (mutation)
                result->set("activation-requested", Element::create(false));
            return createAnswer(rows->empty() ? CONTROL_RESULT_EMPTY : CONTROL_RESULT_SUCCESS,
                                "DHCPv4 scoped option operation completed.", result);
        });
}
} // namespace
int optionNetwork4List(isc::hooks::CalloutHandle& handle) {
    return scopedOptionCommand(handle, Scope::Network, Operation::List);
}
int optionNetwork4Get(isc::hooks::CalloutHandle& handle) {
    return scopedOptionCommand(handle, Scope::Network, Operation::Get);
}
int optionNetwork4Set(isc::hooks::CalloutHandle& handle) {
    return scopedOptionCommand(handle, Scope::Network, Operation::Set);
}
int optionNetwork4Del(isc::hooks::CalloutHandle& handle) {
    return scopedOptionCommand(handle, Scope::Network, Operation::Del);
}
int optionSubnet4List(isc::hooks::CalloutHandle& handle) {
    return scopedOptionCommand(handle, Scope::Subnet, Operation::List);
}
int optionSubnet4Get(isc::hooks::CalloutHandle& handle) {
    return scopedOptionCommand(handle, Scope::Subnet, Operation::Get);
}
int optionSubnet4Set(isc::hooks::CalloutHandle& handle) {
    return scopedOptionCommand(handle, Scope::Subnet, Operation::Set);
}
int optionSubnet4Del(isc::hooks::CalloutHandle& handle) {
    return scopedOptionCommand(handle, Scope::Subnet, Operation::Del);
}
int optionPool4List(isc::hooks::CalloutHandle& handle) {
    return scopedOptionCommand(handle, Scope::Pool, Operation::List);
}
int optionPool4Get(isc::hooks::CalloutHandle& handle) {
    return scopedOptionCommand(handle, Scope::Pool, Operation::Get);
}
int optionPool4Set(isc::hooks::CalloutHandle& handle) {
    return scopedOptionCommand(handle, Scope::Pool, Operation::Set);
}
int optionPool4Del(isc::hooks::CalloutHandle& handle) {
    return scopedOptionCommand(handle, Scope::Pool, Operation::Del);
}
} // namespace kea_db_commands
