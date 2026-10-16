// SPDX-License-Identifier: MPL-2.0
#include <config.h>

#include "commands.h"

#include "arguments.h"
#include "subnet4.h"

#include <cc/command_interpreter.h>
#include <dhcpsrv/config_backend_dhcp4_mgr.h>
#include <hooks/callout_handle.h>
#include <hooks/hooks.h>

namespace kea_db_commands {

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
            try {
                const auto result = listSubnets();
                response =
                    createAnswer(CONTROL_RESULT_SUCCESS, "DHCPv4 subnets retrieved.", result);
            } catch (const ContractError& error) {
                response = createAnswer(CONTROL_RESULT_ERROR, error.what());
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
namespace {
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

} // namespace

int subnet4Get(isc::hooks::CalloutHandle& handle) {
    return subnet4Lookup(handle, false);
}

int subnet4Del(isc::hooks::CalloutHandle& handle) {
    return subnet4Lookup(handle, true);
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
} // namespace kea_db_commands
