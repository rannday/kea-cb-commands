// SPDX-License-Identifier: MPL-2.0
#ifndef KEA_DB_COMMANDS_BACKEND_SUPPORT_H
#define KEA_DB_COMMANDS_BACKEND_SUPPORT_H

#include "command_support.h"

#include <database/backend_selector.h>
#include <database/server_selector.h>
#include <dhcpsrv/cfgmgr.h>

namespace kea_db_commands {

// Typed manager access: no private manager, cached pool, family erasure or SQL.
// A pool is resolved afresh at the operation boundary.
template <typename Manager> auto backendPool() -> decltype(Manager::instance().getPool()) {
    return Manager::instance().getPool();
}

inline isc::db::BackendSelector singleBackendSelector(bool pool_available,
                                                      const isc::dhcp::ConstSrvConfigPtr& config,
                                                      const char* missing_error,
                                                      const char* multiple_error,
                                                      const char* sql_error = nullptr) {
    const auto control = config->getConfigControlInfo();
    if (!pool_available || !control || control->getConfigDatabases().empty()) {
        throw ContractError(missing_error);
    }
    if (control->getConfigDatabases().size() != 1) {
        throw ContractError(multiple_error);
    }
    std::string type;
    control->getConfigDatabases().front().getParameterValue("type", type);
    if (sql_error && type != "postgresql" && type != "mysql") {
        throw ContractError(sql_error);
    }
    // Explicit type makes an absent live backend an error rather than an empty
    // successful read. Never aggregate the native pool's first-nonempty results.
    return isc::db::BackendSelector(isc::db::BackendSelector::stringToBackendType(type));
}

inline isc::data::ServerTag validatedServerTag(const std::string& text) {
    isc::data::ServerTag tag;
    try {
        tag = isc::data::ServerTag(text);
    } catch (...) {
        throw ContractError("Invalid server-tag.");
    }
    if (tag.get() != text) {
        throw ContractError("server-tag must be lowercase without surrounding whitespace.");
    }
    return tag;
}

inline isc::db::ServerSelector serverSelector(const isc::data::ServerTag& tag) {
    return tag.amAll() ? isc::db::ServerSelector::ALL() : isc::db::ServerSelector::ONE(tag.get());
}

} // namespace kea_db_commands

#endif
