// SPDX-License-Identifier: MPL-2.0
#include <config.h>

#include <asiolink/addr_utilities.h>
#include <cc/command_interpreter.h>
#include <dhcpsrv/cfgmgr.h>
#include <dhcpsrv/config_backend_dhcp4_mgr.h>
#include <dhcpsrv/pool.h>
#include <hooks/callout_handle.h>
#include <hooks/hooks.h>
#include <hooks/library_handle.h>
#include <log/logger.h>
#include <log/macros.h>
#include <log/message_initializer.h>
#include <process/daemon.h>
#include <stdexcept>
#include <sys/socket.h>

static_assert(KEA_HOOKS_VERSION == 30201 || KEA_HOOKS_VERSION == 30004,
              "Build against a source-assessed Kea release");

namespace {
isc::log::Logger logger("db-commands");
const char* messages[] = {"DB_COMMANDS_LOADED",
                          "configuration backend commands registered",
                          "DB_COMMANDS_UNLOADED",
                          "diagnostic hook unloaded",
                          "DB_COMMANDS_LOAD_FAILED",
                          "diagnostic hook initialization failed",
                          nullptr};
isc::log::MessageInitializer message_initializer(messages);

int diagnostic(isc::hooks::CalloutHandle& handle) {
    using namespace isc::data;
    using namespace isc::config;
    try {
        ConstElementPtr command;
        handle.getArgument("command", command);
        const auto arguments = command ? command->get("arguments") : ConstElementPtr();
        ConstElementPtr response;
        if (!command || (arguments && (arguments->getType() != Element::map ||
                                       !arguments->mapValue().empty()))) {
            response = createAnswer(CONTROL_RESULT_ERROR,
                                    "This diagnostic accepts only absent or empty arguments.");
        } else {
            // Resolve the server's manager at command time. Do not retain a pool
            // across configuration reloads or initialize SQL connections here.
            const auto pool = isc::dhcp::ConfigBackendDHCPv4Mgr::instance().getPool();
            if (!pool) {
                response = createAnswer(CONTROL_RESULT_ERROR,
                                        "The configuration backend pool is unavailable.");
            } else {
                ElementPtr result = Element::createMap();
                result->set("configuration-backend-pool-accessible", Element::create(true));
                result->set("kea-hooks-version", Element::create(KEA_HOOKS_VERSION));
                result->set("database-connectivity-tested", Element::create(false));
                result->set("mutations-supported", Element::create(true));
                response = createAnswer(CONTROL_RESULT_SUCCESS,
                                        "Configuration backend API is accessible.", result);
            }
        }
        // HookedCommandMgr stores a ConstElementPtr, not an ElementPtr.
        handle.setArgument("response", response);
        return 0;
    } catch (...) {
        // Database exceptions may contain credentials. Do not expose their text.
        try {
            ConstElementPtr response =
                createAnswer(CONTROL_RESULT_ERROR, "Configuration backend diagnostic failed.");
            handle.setArgument("response", response);
            return 0;
        } catch (...) {
            return 1;
        }
    }
}

int subnet4List(isc::hooks::CalloutHandle& handle) {
    using namespace isc::data;
    using namespace isc::config;
    try {
        ConstElementPtr command;
        handle.getArgument("command", command);
        const auto arguments = command ? command->get("arguments") : ConstElementPtr();
        ConstElementPtr response;
        if (!command || (arguments && (arguments->getType() != Element::map ||
                                       !arguments->mapValue().empty()))) {
            response = createAnswer(CONTROL_RESULT_ERROR,
                                    "cb-subnet4-list accepts only absent or empty arguments.");
        } else {
            // Resolve current state on every invocation. Kea's pool returns the
            // first nonempty collection, not an aggregate. Its public API cannot
            // uniquely select databases sharing a type/host/port, so fail closed.
            const auto pool = isc::dhcp::ConfigBackendDHCPv4Mgr::instance().getPool();
            const auto config = isc::dhcp::CfgMgr::instance().getCurrentCfg();
            const auto control = config->getConfigControlInfo();
            if (!pool || !control || control->getConfigDatabases().empty()) {
                response =
                    createAnswer(CONTROL_RESULT_ERROR, "No configuration backend is configured.");
            } else if (control->getConfigDatabases().size() != 1) {
                response = createAnswer(CONTROL_RESULT_ERROR,
                                        "cb-subnet4-list requires exactly one configured backend; "
                                        "multiple backends cannot be listed without ambiguity.");
            } else {
                const auto tag = config->getServerTag();
                const auto selector = tag.empty() ? isc::db::ServerSelector::ALL()
                                                  : isc::db::ServerSelector::ONE(tag);
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
                    response = createAnswer(CONTROL_RESULT_ERROR,
                                            "Shared-network subnets cannot be represented "
                                            "completely by cb-subnet4-list.");
                } else {
                    auto result = Element::createMap();
                    result->set("subnet4", list);
                    result->set("server-tag", Element::create(tag.empty() ? "all" : tag));
                    response =
                        createAnswer(CONTROL_RESULT_SUCCESS, "DHCPv4 subnets retrieved.", result);
                }
            }
        }
        handle.setArgument("response", response);
        return 0;
    } catch (...) {
        // Upstream database exceptions can include connection parameters.
        try {
            ConstElementPtr response = createAnswer(
                CONTROL_RESULT_ERROR, "Configuration backend read failed or unavailable.");
            handle.setArgument("response", response);
            return 0;
        } catch (...) {
            return 1;
        }
    }
}
// Only errors raised by our contract checks may be returned verbatim. Native
// exceptions can contain connection strings and must remain private.
struct ContractError : std::runtime_error {
    using std::runtime_error::runtime_error;
};

// Identity lookups deliberately expose neither ANY nor backend selectors.
isc::data::ConstElementPtr lookupSubnet(const isc::data::ConstElementPtr& arguments,
                                        const bool remove) {
    using namespace isc::data;
    using namespace isc::dhcp;
    using namespace isc::db;
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

int subnet4Lookup(isc::hooks::CalloutHandle& handle, const bool remove) {
    using namespace isc::data;
    using namespace isc::config;
    try {
        ConstElementPtr response;
        try {
            ConstElementPtr command;
            handle.getArgument("command", command);
            const auto result =
                lookupSubnet(command ? command->get("arguments") : ConstElementPtr(), remove);
            const bool found = remove ? result->get("deleted")->intValue() != 0
                                      : !result->get("subnet4")->listValue().empty();
            response = createAnswer(
                found ? CONTROL_RESULT_SUCCESS : CONTROL_RESULT_EMPTY,
                found ? (remove ? "DHCPv4 subnet deleted; leases retained; activation required."
                                : "DHCPv4 subnet retrieved.")
                      : "DHCPv4 subnet not found.",
                result);
        } catch (const ContractError& error) {
            response = createAnswer(CONTROL_RESULT_ERROR, error.what());
        } catch (...) {
            response = createAnswer(CONTROL_RESULT_ERROR,
                                    remove ? "Configuration backend deletion failed or "
                                             "unavailable; reconcile backend state before retrying."
                                           : "Configuration backend read failed or unavailable.");
        }
        handle.setArgument("response", response);
        return 0;
    } catch (...) {
        return 1;
    }
}

int subnet4Get(isc::hooks::CalloutHandle& handle) {
    return subnet4Lookup(handle, false);
}

int subnet4Del(isc::hooks::CalloutHandle& handle) {
    return subnet4Lookup(handle, true);
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

int subnet4Set(isc::hooks::CalloutHandle& handle) {
    using namespace isc::data;
    using namespace isc::config;
    try {
        ConstElementPtr response;
        try {
            ConstElementPtr command;
            handle.getArgument("command", command);
            const auto result = setSubnet(command ? command->get("arguments") : ConstElementPtr());
            response = createAnswer(CONTROL_RESULT_SUCCESS, "DHCPv4 subnet persisted.", result);
        } catch (const ContractError& error) {
            response = createAnswer(CONTROL_RESULT_ERROR, error.what());
        } catch (...) {
            response = createAnswer(CONTROL_RESULT_ERROR,
                                    "Configuration backend write failed or unavailable; "
                                    "reconcile backend state before retrying.");
        }
        handle.setArgument("response", response);
        return 0;
    } catch (...) {
        return 1;
    }
}
} // namespace

#define DB_COMMANDS_EXPORT extern "C" __attribute__((visibility("default")))

DB_COMMANDS_EXPORT int version() {
    return KEA_HOOKS_VERSION;
}

DB_COMMANDS_EXPORT int multi_threading_compatible() {
    return 1;
}

DB_COMMANDS_EXPORT int load(isc::hooks::LibraryHandle& handle) {
    try {
        if (isc::dhcp::CfgMgr::instance().getFamily() != AF_INET ||
            isc::process::Daemon::getProcName() != "kea-dhcp4") {
            return 1;
        }
        handle.registerCommandCallout("db-commands-diagnostic", diagnostic);
        handle.registerCommandCallout("cb-subnet4-list", subnet4List);
        handle.registerCommandCallout("cb-subnet4-get", subnet4Get);
        handle.registerCommandCallout("cb-subnet4-del", subnet4Del);
        handle.registerCommandCallout("cb-subnet4-set", subnet4Set);
        LOG_INFO(logger, "DB_COMMANDS_LOADED");
        return 0;
    } catch (...) {
        try {
            LOG_ERROR(logger, "DB_COMMANDS_LOAD_FAILED");
        } catch (...) {
        }
        return 1;
    }
}

DB_COMMANDS_EXPORT int unload() {
    try {
        LOG_INFO(logger, "DB_COMMANDS_UNLOADED");
        // Kea removes registered callouts during library teardown.
        return 0;
    } catch (...) {
        return 1;
    }
}
