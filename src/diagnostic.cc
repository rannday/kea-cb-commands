// SPDX-License-Identifier: MPL-2.0
#include <config.h>

#include <cc/command_interpreter.h>
#include <dhcpsrv/cfgmgr.h>
#include <dhcpsrv/config_backend_dhcp4_mgr.h>
#include <hooks/callout_handle.h>
#include <hooks/hooks.h>
#include <hooks/library_handle.h>
#include <log/logger.h>
#include <log/macros.h>
#include <log/message_initializer.h>
#include <process/daemon.h>
#include <sys/socket.h>

static_assert(KEA_HOOKS_VERSION == 30201 || KEA_HOOKS_VERSION == 30004,
              "Build against a source-assessed Kea release");

namespace {
isc::log::Logger logger("db-commands");
const char* messages[] = {"DB_COMMANDS_LOADED",
                          "diagnostic command registered (no SQL mutations)",
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
                result->set("mutations-supported", Element::create(false));
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
} // namespace

#define DB_COMMANDS_EXPORT extern "C" __attribute__((visibility("default")))

DB_COMMANDS_EXPORT int version() { return KEA_HOOKS_VERSION; }

DB_COMMANDS_EXPORT int multi_threading_compatible() { return 1; }

DB_COMMANDS_EXPORT int load(isc::hooks::LibraryHandle& handle) {
    try {
        if (isc::dhcp::CfgMgr::instance().getFamily() != AF_INET ||
            isc::process::Daemon::getProcName() != "kea-dhcp4") {
            return 1;
        }
        handle.registerCommandCallout("db-commands-diagnostic", diagnostic);
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
