// SPDX-License-Identifier: MPL-2.0
#include <config.h>

#include "subnet4.h"

#include "arguments.h"

#include <dhcpsrv/cfgmgr.h>
#include <dhcpsrv/config_backend_dhcp4_mgr.h>
#include <dhcpsrv/pool.h>

namespace kea_db_commands {

isc::data::ConstElementPtr listSubnets() {
    using namespace isc::data;
    // Resolve current state on every invocation. Kea's pool returns the
    // first nonempty collection, not an aggregate. Its public API cannot
    // uniquely select databases sharing a type/host/port, so fail closed.
    const auto pool = isc::dhcp::ConfigBackendDHCPv4Mgr::instance().getPool();
    const auto config = isc::dhcp::CfgMgr::instance().getCurrentCfg();
    const auto control = config->getConfigControlInfo();
    if (!pool || !control || control->getConfigDatabases().empty()) {
        throw ContractError("No configuration backend is configured.");
    } else if (control->getConfigDatabases().size() != 1) {
        throw ContractError("cb-subnet4-list requires exactly one configured backend; "
                            "multiple backends cannot be listed without ambiguity.");
    } else {
        const auto tag = config->getServerTag();
        const auto selector =
            tag.empty() ? isc::db::ServerSelector::ALL() : isc::db::ServerSelector::ONE(tag);
        std::string type;
        control->getConfigDatabases().front().getParameterValue("type", type);
        // An explicit type also makes an absent live backend an error
        // during native recovery instead of a successful empty result.
        const auto subnets = pool->getAllSubnets4(
            isc::db::BackendSelector(isc::db::BackendSelector::stringToBackendType(type)),
            selector);
        auto list = Element::createList();
        bool shared_network = false;
        for (const auto& subnet : subnets) {
            if (!subnet->getSharedNetworkName().empty()) {
                shared_network = true;
                break;
            }
            list->add(subnet->toElement());
        }
        if (shared_network) {
            throw ContractError("Shared-network subnets cannot be represented "
                                "completely by cb-subnet4-list.");
        } else {
            auto result = Element::createMap();
            result->set("subnet4", list);
            result->set("server-tag", Element::create(tag.empty() ? "all" : tag));
            return result;
        }
    }
}

// Identity lookups deliberately expose neither ANY nor backend selectors.
isc::data::ConstElementPtr lookupSubnet(const isc::data::ConstElementPtr& arguments,
                                        const bool remove) {
    using namespace isc::data;
    using namespace isc::dhcp;
    using namespace isc::db;
    validateLookupArguments(arguments, remove);
    const auto id = arguments->get("id");
    const auto prefix = arguments->get("subnet");
    const auto tag_element = arguments->get("server-tag");
    const auto config = CfgMgr::instance().getCurrentCfg();
    std::string tag_text = config->getServerTag();
    if (tag_text.empty()) {
        tag_text = "all";
    }
    if (tag_element) {
        if (tag_element->getType() != Element::string) {
            throw ContractError("server-tag must be an explicit string.");
        }
        tag_text = tag_element->stringValue();
    }
    ServerTag tag;
    try {
        tag = ServerTag(tag_text);
    } catch (...) {
        throw ContractError("Invalid server-tag.");
    }
    if (tag.get() != tag_text) {
        throw ContractError("server-tag must be lowercase without surrounding whitespace.");
    }
    const auto pool = ConfigBackendDHCPv4Mgr::instance().getPool();
    const auto control = config->getConfigControlInfo();
    if (!pool || !control || control->getConfigDatabases().size() != 1) {
        throw ContractError("Subnet lookup/deletion requires exactly one configured SQL backend.");
    }
    std::string type;
    control->getConfigDatabases().front().getParameterValue("type", type);
    if (type != "postgresql" && type != "mysql") {
        throw ContractError("Subnet lookup/deletion requires a PostgreSQL or MySQL backend.");
    }
    const BackendSelector backend(BackendSelector::stringToBackendType(type));
    const auto selector = tag.amAll() ? ServerSelector::ALL() : ServerSelector::ONE(tag.get());
    // A tagged read includes universal rows. Deletion must inspect every
    // association before invoking the native exact-tag whole-row deletion.
    const auto lookup = remove ? ServerSelector::ANY() : selector;
    const auto subnet = id ? pool->getSubnet4(backend, lookup, SubnetID(id->intValue()))
                           : pool->getSubnet4(backend, lookup, prefix->stringValue());
    if (subnet && !subnet->getSharedNetworkName().empty()) {
        throw ContractError("Shared-network subnets cannot be represented completely.");
    }
    auto result = Element::createMap();
    result->set("server-tag", Element::create(tag.get()));
    if (remove) {
        if (!tag.amAll() && !pool->getServer4(backend, tag)) {
            throw ContractError("server-tag must already exist in the configuration backend.");
        }
        uint64_t count = 0;
        if (subnet) {
            const auto tags = subnet->getServerTags();
            if (tags.size() != 1 || tags.begin()->get() != tag.get()) {
                throw ContractError("Deletion requires one exact server-tag association.");
            }
            // Native backend owns transaction, audit and cascading children.
            // Independent writers must be serialized with this preflight.
            count = id ? pool->deleteSubnet4(backend, selector, SubnetID(id->intValue()))
                       : pool->deleteSubnet4(backend, selector, prefix->stringValue());
        }
        result->set("deleted", Element::create(static_cast<int64_t>(count)));
        result->set("leases-deleted", Element::create(false));
        result->set("activation-requested", Element::create(false));
        return result;
    }
    // Keep the same native subnet list shape used by cb-subnet4-list.
    auto list = Element::createList();
    if (subnet) {
        list->add(subnet->toElement());
    }
    result->set("subnet4", list);
    return result;
}

isc::data::ConstElementPtr setSubnet(const isc::data::ConstElementPtr& arguments) {
    using namespace isc::data;
    using namespace isc::dhcp;
    using namespace isc::db;
    if (!arguments || arguments->getType() != Element::map || arguments->mapValue().size() != 2 ||
        !arguments->get("server-tag") || !arguments->get("subnet4")) {
        throw ContractError("Expected only server-tag and one subnet4 map.");
    }
    const auto tag_element = arguments->get("server-tag");
    if (tag_element->getType() != Element::string) {
        throw ContractError("server-tag must be an explicit string.");
    }
    ServerTag tag;
    try {
        tag = ServerTag(tag_element->stringValue());
    } catch (...) {
        throw ContractError("Invalid server-tag.");
    }
    // Avoid implicit tag normalization changing the requested association.
    if (tag.get() != tag_element->stringValue()) {
        throw ContractError("server-tag must be lowercase without surrounding whitespace.");
    }
    const auto input = arguments->get("subnet4");
    const auto subnet = parseSubnet4(input);
    const auto pools = input->get("pools");
    const auto pool = ConfigBackendDHCPv4Mgr::instance().getPool();
    const auto control = CfgMgr::instance().getCurrentCfg()->getConfigControlInfo();
    if (!pool || !control || control->getConfigDatabases().size() != 1) {
        throw ContractError("cb-subnet4-set requires exactly one configured SQL backend.");
    }
    std::string type;
    control->getConfigDatabases().front().getParameterValue("type", type);
    if (type != "postgresql" && type != "mysql") {
        throw ContractError("cb-subnet4-set requires a PostgreSQL or MySQL backend.");
    }
    const BackendSelector backend(BackendSelector::stringToBackendType(type));
    // Native getServer4 excludes the schema's reserved universal server.
    if (!tag.amAll() && !pool->getServer4(backend, tag)) {
        throw ContractError("server-tag must already exist in the configuration backend.");
    }
    // ANY is essential: ONE also includes universal objects and hides objects
    // belonging to other servers. Prefix conflicts must never rename another ID.
    const auto existing = pool->getSubnet4(backend, ServerSelector::ANY(), subnet->getID());
    const auto by_prefix = pool->getSubnet4(backend, ServerSelector::ANY(), subnet->toText());
    if (by_prefix && by_prefix->getID() != subnet->getID()) {
        throw ContractError("The prefix already belongs to another subnet ID.");
    }
    if (existing) {
        const auto tags = existing->getServerTags();
        if (tags.size() != 1 || tags.begin()->get() != tag.get()) {
            throw ContractError("Updating subnet server associations is unsupported.");
        }
        const auto baseline = Subnet4::create(
            existing->get().first, existing->get().second, 0, 0,
            existing->getValid(isc::dhcp::Network::Inheritance::NONE), existing->getID());
        for (const auto& stored_pool : existing->getPools(Lease::TYPE_V4)) {
            // Comparing against basic native pools rejects pool options, classes,
            // context and other unsupported settings before whole-object writes.
            baseline->addPool(
                Pool4::create(stored_pool->getFirstAddress(), stored_pool->getLastAddress()));
        }
        if (!existing->getSharedNetworkName().empty() ||
            !existing->toElement()->equals(*baseline->toElement())) {
            throw ContractError(
                "Existing subnet contains unsupported configuration; update refused.");
        }
        if (!pools) {
            try {
                for (const auto& stored_pool : existing->getPools(Lease::TYPE_V4)) {
                    subnet->addPool(stored_pool);
                }
            } catch (...) {
                throw ContractError(
                    "Existing pools do not fit the requested subnet; supply replacement pools.");
            }
        }
    }
    // The native backend owns the transaction, audit revision and rollback.
    // Preflight reads are not locked against independent external writers.
    pool->createUpdateSubnet4(
        backend, tag.amAll() ? ServerSelector::ALL() : ServerSelector::ONE(tag.get()), subnet);
    auto result = Element::createMap();
    result->set("subnet4", input);
    result->set("server-tag", Element::create(tag.get()));
    result->set("persisted", Element::create(true));
    result->set("activation-requested", Element::create(false));
    return result;
}

} // namespace kea_db_commands
