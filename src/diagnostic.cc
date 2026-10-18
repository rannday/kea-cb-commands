// SPDX-License-Identifier: MPL-2.0
#include <config.h>

#include "commands.h"

#include <dhcpsrv/cfgmgr.h>
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
bool allow_mutations = false;
isc::log::Logger logger("db-commands");
const char* messages[] = {"DB_COMMANDS_LOADED",
                          "configuration backend commands registered",
                          "DB_COMMANDS_UNLOADED",
                          "diagnostic hook unloaded",
                          "DB_COMMANDS_LOAD_FAILED",
                          "diagnostic hook initialization failed",
                          nullptr};
isc::log::MessageInitializer message_initializer(messages);

} // namespace

namespace kea_db_commands {
bool mutationsAllowed() {
    return allow_mutations;
}
} // namespace kea_db_commands

#define DB_COMMANDS_EXPORT extern "C" __attribute__((visibility("default")))

DB_COMMANDS_EXPORT int version() {
    return KEA_HOOKS_VERSION;
}

DB_COMMANDS_EXPORT int multi_threading_compatible() {
    return 1;
}

DB_COMMANDS_EXPORT int load(isc::hooks::LibraryHandle& handle) {
    using namespace kea_db_commands;
    allow_mutations = false;
    try {
        if (isc::dhcp::CfgMgr::instance().getFamily() != AF_INET ||
            isc::process::Daemon::getProcName() != "kea-dhcp4") {
            return 1;
        }
        bool requested = false;
        const auto parameters = handle.getParameters();
        if (parameters) {
            if (parameters->getType() != isc::data::Element::map) {
                return 1;
            }
            for (const auto& parameter : parameters->mapValue()) {
                if (parameter.first != "allow-mutations" ||
                    parameter.second->getType() != isc::data::Element::boolean) {
                    LOG_ERROR(logger, "DB_COMMANDS_LOAD_FAILED");
                    return 1;
                }
                requested = parameter.second->boolValue();
            }
        }
        handle.registerCommandCallout("db-commands-diagnostic", diagnostic);
        handle.registerCommandCallout("cb-subnet4-list", subnet4List);
        handle.registerCommandCallout("cb-subnet4-get", subnet4Get);
        handle.registerCommandCallout("cb-subnet4-del", subnet4Del);
        handle.registerCommandCallout("cb-subnet4-set", subnet4Set);
        handle.registerCommandCallout("cb-server4-list", server4List);
        handle.registerCommandCallout("cb-server4-get", server4Get);
        handle.registerCommandCallout("cb-server4-set", server4Set);
        handle.registerCommandCallout("cb-server4-del", server4Del);
        handle.registerCommandCallout("cb-global-parameter4-list", global4List);
        handle.registerCommandCallout("cb-global-parameter4-get", global4Get);
        handle.registerCommandCallout("cb-global-parameter4-set", global4Set);
        handle.registerCommandCallout("cb-global-parameter4-del", global4Del);
        LOG_INFO(logger, "DB_COMMANDS_LOADED");
        allow_mutations = requested;
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
    allow_mutations = false;
    try {
        LOG_INFO(logger, "DB_COMMANDS_UNLOADED");
        // Kea removes registered callouts during library teardown.
        return 0;
    } catch (...) {
        return 1;
    }
}
