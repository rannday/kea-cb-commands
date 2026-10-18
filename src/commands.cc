// SPDX-License-Identifier: MPL-2.0
#include <config.h>

#include "commands.h"

#include "backend_support.h"
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
        const auto request = commandRequest(handle);
        ConstElementPtr response;
        if (!request.acceptsEmptyArguments()) {
            response = createAnswer(CONTROL_RESULT_ERROR,
                                    "This diagnostic accepts only absent or empty arguments.");
        } else {
            // Resolve the server's manager at command time. Do not retain a pool
            // across configuration reloads or initialize SQL connections here.
            const auto pool = backendPool<isc::dhcp::ConfigBackendDHCPv4Mgr>();
            if (!pool) {
                response = createAnswer(CONTROL_RESULT_ERROR,
                                        "The configuration backend pool is unavailable.");
            } else {
                ElementPtr result = Element::createMap();
                result->set("configuration-backend-pool-accessible", Element::create(true));
                result->set("kea-hooks-version", Element::create(KEA_HOOKS_VERSION));
                result->set("database-connectivity-tested", Element::create(false));
                result->set("mutations-supported", Element::create(true));
                result->set("allow-mutations", Element::create(mutationsAllowed()));
                response = createAnswer(CONTROL_RESULT_SUCCESS,
                                        "Configuration backend API is accessible.", result);
            }
        }
        // HookedCommandMgr stores a ConstElementPtr, not an ElementPtr.
        return respond(handle, response);
    } catch (...) {
        // Database exceptions may contain credentials. Do not expose their text.
        try {
            ConstElementPtr response =
                createAnswer(CONTROL_RESULT_ERROR, "Configuration backend diagnostic failed.");
            return respond(handle, response);
        } catch (...) {
            return 1;
        }
    }
}

int subnet4List(isc::hooks::CalloutHandle& handle) {
    using namespace isc::data;
    using namespace isc::config;
    try {
        const auto request = commandRequest(handle);
        ConstElementPtr response;
        if (!request.acceptsEmptyArguments()) {
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
        return respond(handle, response);
    } catch (...) {
        // Upstream database exceptions can include connection parameters.
        try {
            ConstElementPtr response = createAnswer(
                CONTROL_RESULT_ERROR, "Configuration backend read failed or unavailable.");
            return respond(handle, response);
        } catch (...) {
            return 1;
        }
    }
}
namespace {
int subnet4Lookup(isc::hooks::CalloutHandle& handle, const bool remove) {
    using namespace isc::config;
    return commandBoundary(
        handle,
        remove ? "Configuration backend deletion failed or unavailable; reconcile backend state "
                 "before retrying."
               : "Configuration backend read failed or unavailable.",
        [&]() {
            if (remove) {
                requireMutationAdmission();
            }
            const auto result = lookupSubnet(commandRequest(handle).arguments, remove);
            const bool found = remove ? result->get("deleted")->intValue() != 0
                                      : !result->get("subnet4")->listValue().empty();
            return createAnswer(
                found ? CONTROL_RESULT_SUCCESS : CONTROL_RESULT_EMPTY,
                found ? (remove ? "DHCPv4 subnet deleted; leases retained; activation required."
                                : "DHCPv4 subnet retrieved.")
                      : "DHCPv4 subnet not found.",
                result);
        });
}

} // namespace

int subnet4Get(isc::hooks::CalloutHandle& handle) {
    return subnet4Lookup(handle, false);
}

int subnet4Del(isc::hooks::CalloutHandle& handle) {
    return subnet4Lookup(handle, true);
}

int subnet4Set(isc::hooks::CalloutHandle& handle) {
    using namespace isc::config;
    return commandBoundary(handle,
                           "Configuration backend write failed or unavailable; reconcile backend "
                           "state before retrying.",
                           [&]() {
                               requireMutationAdmission();
                               const auto result = setSubnet(commandRequest(handle).arguments);
                               return createAnswer(CONTROL_RESULT_SUCCESS,
                                                   "DHCPv4 subnet persisted.", result);
                           });
}
} // namespace kea_db_commands
