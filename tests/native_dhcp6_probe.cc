// Compile/link probe for the pinned public Kea 3.2.1 DHCPv6 backend API.
// This executable never configures a backend or invokes a database operation.
#include <config.h>

#include "../src/backend_support.h"

#include <cc/stamped_value.h>
#include <database/backend_selector.h>
#include <database/server.h>
#include <database/server_selector.h>
#include <dhcpsrv/config_backend_dhcp6_mgr.h>
#include <hooks/hooks.h>

#include <cstdint>
#include <iostream>

static_assert(KEA_HOOKS_VERSION == 30201, "The DHCPv6 probe requires Kea 3.2.1");
static_assert(__cplusplus == 201402L, "The DHCPv6 probe requires C++14");

// Qualified calls bypass virtual dispatch so the linker must resolve the pool
// implementations, rather than merely compile calls through a vtable. main()
// retains this function's address but never calls it. No command-line argument
// or environment variable can enable these read/write operations.
void linkDhcp6Operations(isc::dhcp::ConfigBackendPoolDHCPv6& pool,
                         const isc::db::BackendSelector& backend,
                         const isc::db::ServerSelector& servers, const isc::data::ServerTag& tag,
                         const isc::db::ServerPtr& server,
                         const isc::data::StampedValuePtr& value) {
    const isc::db::ServerCollection all_servers =
        pool.isc::dhcp::ConfigBackendPoolDHCPv6::getAllServers6(backend);
    const isc::db::ServerPtr one_server =
        pool.isc::dhcp::ConfigBackendPoolDHCPv6::getServer6(backend, tag);
    const isc::data::StampedValueCollection globals =
        pool.isc::dhcp::ConfigBackendPoolDHCPv6::getAllGlobalParameters6(backend, servers);
    const isc::data::StampedValuePtr global =
        pool.isc::dhcp::ConfigBackendPoolDHCPv6::getGlobalParameter6(backend, servers,
                                                                     "valid-lifetime");
    pool.isc::dhcp::ConfigBackendPoolDHCPv6::createUpdateServer6(backend, server);
    pool.isc::dhcp::ConfigBackendPoolDHCPv6::createUpdateGlobalParameter6(backend, servers, value);
    const uint64_t deleted_server =
        pool.isc::dhcp::ConfigBackendPoolDHCPv6::deleteServer6(backend, tag);
    const uint64_t deleted_servers =
        pool.isc::dhcp::ConfigBackendPoolDHCPv6::deleteAllServers6(backend);
    const uint64_t deleted_global = pool.isc::dhcp::ConfigBackendPoolDHCPv6::deleteGlobalParameter6(
        backend, servers, "valid-lifetime");
    const uint64_t deleted_globals =
        pool.isc::dhcp::ConfigBackendPoolDHCPv6::deleteAllGlobalParameters6(backend, servers);
    (void)all_servers;
    (void)one_server;
    (void)globals;
    (void)global;
    (void)deleted_server;
    (void)deleted_servers;
    (void)deleted_global;
    (void)deleted_globals;
}

int main() {
    // Volatile storage retains the operation body and its shared-library
    // references in optimized builds without executing the function.
    auto* volatile operations = &linkDhcp6Operations;
    const auto pool = kea_db_commands::backendPool<isc::dhcp::ConfigBackendDHCPv6Mgr>();
    const isc::db::BackendSelector postgresql(
        isc::db::BackendSelector::stringToBackendType("postgresql"));
    const isc::db::BackendSelector mysql(isc::db::BackendSelector::stringToBackendType("mysql"));
    const auto all = isc::db::ServerSelector::ALL();
    const auto one = isc::db::ServerSelector::ONE("probe");
    const auto any = isc::db::ServerSelector::ANY();
    const auto unassigned = isc::db::ServerSelector::UNASSIGNED();
    const auto multiple = isc::db::ServerSelector::MULTIPLE({"probe-a", "probe-b"});
    (void)postgresql;
    (void)mysql;
    (void)all;
    (void)one;
    (void)any;
    (void)unassigned;
    (void)multiple;
    if (!pool || !operations) {
        return 1;
    }
    std::cout << "PASS: Kea 3.2.1 DHCPv6 manager, selectors and server/global API link; "
                 "no backend operations executed\n";
    return 0;
}
