cmake_minimum_required(VERSION 3.20)
project(kea_db_commands VERSION 0.1.0 LANGUAGES CXX)

if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux")
    message(FATAL_ERROR "This hook targets Linux Kea. Build inside Linux or WSL2.")
endif()

if(NOT DEFINED CMAKE_CXX_STANDARD)
    set(CMAKE_CXX_STANDARD 14)
endif()
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(PkgConfig REQUIRED)
pkg_check_modules(KEA REQUIRED IMPORTED_TARGET kea)
# A private static copy of Kea would have different singleton state.
foreach(library IN LISTS KEA_LINK_LIBRARIES)
    if(library MATCHES "\\.a$")
        message(FATAL_ERROR "Kea must use shared libraries, found: ${library}")
    endif()
endforeach()

include(CheckCXXSourceCompiles)
set(CMAKE_REQUIRED_LIBRARIES PkgConfig::KEA)
check_cxx_source_compiles([=[
    #include <config.h>
    #include <hooks/hooks.h>
    #include <dhcpsrv/cfgmgr.h>
    #include <dhcpsrv/config_backend_dhcp4_mgr.h>
    static_assert(KEA_HOOKS_VERSION == 30201 || KEA_HOOKS_VERSION == 30004,
                  "Only Kea 3.2.1 and 3.0.4 have been source-assessed");
    int main() {
        auto pool = isc::dhcp::ConfigBackendDHCPv4Mgr::instance().getPool();
        if (pool) {
            auto subnets = pool->getAllSubnets4(
                isc::db::BackendSelector(isc::db::BackendSelector::stringToBackendType("mysql")),
                isc::db::ServerSelector::ALL());
            for (const auto& subnet : subnets) {
                subnet->toElement();
                subnet->getSharedNetworkName();
            }
            auto config = isc::dhcp::CfgMgr::instance().getCurrentCfg();
            auto control = config->getConfigControlInfo();
            if (control && !control->getConfigDatabases().empty()) {
                std::string type;
                control->getConfigDatabases().front().getParameterValue("type", type);
            }
        }
        return pool ? 0 : 1;
    }
]=] KEA_DB_COMMANDS_API_LINKS)
unset(CMAKE_REQUIRED_LIBRARIES)
if(NOT KEA_DB_COMMANDS_API_LINKS)
    message(FATAL_ERROR "Required Kea headers/API do not compile and link. See CMakeFiles/CMakeConfigureLog.yaml or CMakeError.log.")
endif()

add_library(kea_db_commands MODULE
    src/diagnostic.cc
    src/commands.cc
    src/arguments.cc
    src/subnet4.cc)
set_target_properties(kea_db_commands PROPERTIES
    OUTPUT_NAME dhcp_db_commands
    CXX_VISIBILITY_PRESET hidden
    VISIBILITY_INLINES_HIDDEN YES)
target_link_libraries(kea_db_commands PRIVATE PkgConfig::KEA)
target_compile_options(kea_db_commands PRIVATE -Wall -Wextra -Wpedantic)
option(KEA_DB_COMMANDS_WARNINGS_AS_ERRORS "Treat hook compiler warnings as errors" OFF)
if(KEA_DB_COMMANDS_WARNINGS_AS_ERRORS)
    target_compile_options(kea_db_commands PRIVATE -Werror)
endif()
option(KEA_DB_COMMANDS_SANITIZERS "Instrument the hook with GCC ASan and UBSan (development only)" OFF)
if(KEA_DB_COMMANDS_SANITIZERS)
    if(NOT CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
        message(FATAL_ERROR "The sanitizer runner currently supports GCC runtimes only")
    endif()
    target_compile_options(kea_db_commands PRIVATE
        -fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer -g)
    target_link_options(kea_db_commands PRIVATE
        -fsanitize=address,undefined -fno-sanitize-recover=all)
endif()
# Keep checkout paths out of __FILE__ and debug information. Runtime library
# discovery is explicit (LD_LIBRARY_PATH or the administrator's loader setup).
target_compile_options(kea_db_commands PRIVATE
    "-ffile-prefix-map=${CMAKE_CURRENT_BINARY_DIR}=./build"
    "-ffile-prefix-map=${CMAKE_CURRENT_SOURCE_DIR}=.")
set_target_properties(kea_db_commands PROPERTIES SKIP_BUILD_RPATH YES INSTALL_RPATH "")
target_link_options(kea_db_commands PRIVATE -Wl,-z,defs)

include(GNUInstallDirs)
install(TARGETS kea_db_commands LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}/kea/hooks)

# Release metadata is separate from Kea's required version() ABI export.
file(GENERATE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/release-build.json" CONTENT
"{
  \"version\": \"${PROJECT_VERSION}\",
  \"kea_version\": \"${KEA_VERSION}\",
  \"build_type\": \"${CMAKE_BUILD_TYPE}\",
  \"cxx_standard\": \"${CMAKE_CXX_STANDARD}\",
  \"compiler\": \"${CMAKE_CXX_COMPILER_ID} ${CMAKE_CXX_COMPILER_VERSION}\",
  \"system\": \"${CMAKE_SYSTEM_NAME}\",
  \"architecture\": \"${CMAKE_SYSTEM_PROCESSOR}\"
}
")

include(CTest)
if(BUILD_TESTING)
    find_package(Python3 REQUIRED COMPONENTS Interpreter)
    string(JOIN ":" KEA_TEST_LIBRARY_PATH ${KEA_LIBRARY_DIRS})
    add_test(NAME control_transport
        COMMAND ${Python3_EXECUTABLE} -B -m unittest discover
                -s ${CMAKE_CURRENT_SOURCE_DIR}/tests -p test_transport.py)
    option(KEA_DB_COMMANDS_RUNTIME_TESTS "Run a matching Kea DHCPv4 process" OFF)
    if(KEA_DB_COMMANDS_RUNTIME_TESTS)
        find_program(KEA_DHCP4_EXECUTABLE NAMES kea-dhcp4 REQUIRED)
        add_test(NAME hook_lifecycle
            COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/smoke.py
                --server ${KEA_DHCP4_EXECUTABLE}
                --hook $<TARGET_FILE:kea_db_commands>
                --work-dir ${CMAKE_CURRENT_BINARY_DIR}/runtime)
        set_tests_properties(hook_lifecycle PROPERTIES TIMEOUT 90
            ENVIRONMENT "LD_LIBRARY_PATH=${KEA_TEST_LIBRARY_PATH}:$ENV{LD_LIBRARY_PATH}")
    endif()
    option(KEA_DB_COMMANDS_POSTGRESQL_TESTS "Run isolated real PostgreSQL integration" OFF)
    option(KEA_DB_COMMANDS_DHCP_TESTS "Run real DHCP in disposable Linux namespaces" OFF)
    if(KEA_DB_COMMANDS_DHCP_TESTS)
        find_program(KEA_LFC_EXECUTABLE NAMES kea-lfc)
    endif()
    if(KEA_DB_COMMANDS_POSTGRESQL_TESTS)
        set(KEA_POSTGRESQL_BIN_DIR "" CACHE PATH "PostgreSQL server binary directory")
        set(KEA_POSTGRESQL_HOOK "" CACHE FILEPATH "Matching Kea libdhcp_pgsql.so")
        set(KEA_POSTGRESQL_SCHEMA "" CACHE FILEPATH "Kea 3.2.1 dhcpdb_create.pgsql")
        find_program(KEA_DHCP4_EXECUTABLE NAMES kea-dhcp4)
        add_test(NAME postgresql_read
            COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/postgresql.py
                --server "${KEA_DHCP4_EXECUTABLE}"
                --hook $<TARGET_FILE:kea_db_commands>
                --pgsql-hook "${KEA_POSTGRESQL_HOOK}"
                --schema "${KEA_POSTGRESQL_SCHEMA}"
                --pg-bin "${KEA_POSTGRESQL_BIN_DIR}"
                --work-dir ${CMAKE_CURRENT_BINARY_DIR}/postgresql)
        set_tests_properties(postgresql_read PROPERTIES TIMEOUT 180 SKIP_RETURN_CODE 77
            LABELS PostgreSQL)
        # Staging upstream's hook changes its relative $ORIGIN search paths.
        # Use the exact matching pkg-config libraries for this test process only.
        string(JOIN ":" KEA_TEST_LIBRARY_PATH ${KEA_LIBRARY_DIRS})
        set_tests_properties(postgresql_read PROPERTIES
            ENVIRONMENT "LD_LIBRARY_PATH=${KEA_TEST_LIBRARY_PATH}:$ENV{LD_LIBRARY_PATH}")
        if(KEA_DB_COMMANDS_DHCP_TESTS)
            add_test(NAME postgresql_dhcp
                COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/packet_namespace.py
                    ${CMAKE_CURRENT_SOURCE_DIR}/tests/postgresql.py --packet
                    --lfc "${KEA_LFC_EXECUTABLE}"
                    --server "${KEA_DHCP4_EXECUTABLE}"
                    --hook $<TARGET_FILE:kea_db_commands>
                    --pgsql-hook "${KEA_POSTGRESQL_HOOK}"
                    --schema "${KEA_POSTGRESQL_SCHEMA}"
                    --pg-bin "${KEA_POSTGRESQL_BIN_DIR}"
                    --work-dir ${CMAKE_CURRENT_BINARY_DIR}/postgresql-dhcp)
            set_tests_properties(postgresql_dhcp PROPERTIES TIMEOUT 240 SKIP_RETURN_CODE 77
                LABELS "PostgreSQL;DHCP"
                ENVIRONMENT "LD_LIBRARY_PATH=${KEA_TEST_LIBRARY_PATH}:$ENV{LD_LIBRARY_PATH}")
        endif()
    endif()
    option(KEA_DB_COMMANDS_MYSQL_TESTS "Run isolated real MySQL/MariaDB integration" OFF)
    if(KEA_DB_COMMANDS_MYSQL_TESTS)
        set(KEA_MYSQL_CLIENT "" CACHE FILEPATH "mysql or mariadb client executable")
        set(KEA_MYSQL_SERVER "" CACHE FILEPATH "mysqld or mariadbd executable")
        set(KEA_MYSQL_INSTALL_DB "" CACHE FILEPATH "mysql_install_db or mariadb-install-db")
        set(KEA_MYSQL_HOOK "" CACHE FILEPATH "Matching Kea libdhcp_mysql.so")
        set(KEA_MYSQL_SCHEMA "" CACHE FILEPATH "Kea 3.2.1 dhcpdb_create.mysql")
        find_program(KEA_DHCP4_EXECUTABLE NAMES kea-dhcp4)
        add_test(NAME mysql_read
            COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/mysql.py
                --server "${KEA_DHCP4_EXECUTABLE}"
                --hook $<TARGET_FILE:kea_db_commands>
                --mysql-hook "${KEA_MYSQL_HOOK}"
                --schema "${KEA_MYSQL_SCHEMA}"
                --mysql-bin "${KEA_MYSQL_CLIENT}"
                --mysql-install-db "${KEA_MYSQL_INSTALL_DB}"
                --mysql-server "${KEA_MYSQL_SERVER}"
                --work-dir ${CMAKE_CURRENT_BINARY_DIR}/mysql)
        set_tests_properties(mysql_read PROPERTIES TIMEOUT 180 SKIP_RETURN_CODE 77
            LABELS MySQL)
        string(JOIN ":" KEA_TEST_LIBRARY_PATH ${KEA_LIBRARY_DIRS})
        set_tests_properties(mysql_read PROPERTIES
            ENVIRONMENT "LD_LIBRARY_PATH=${KEA_TEST_LIBRARY_PATH}:$ENV{LD_LIBRARY_PATH}")
        if(KEA_DB_COMMANDS_DHCP_TESTS)
            add_test(NAME mysql_dhcp
                COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/packet_namespace.py
                    ${CMAKE_CURRENT_SOURCE_DIR}/tests/mysql.py --packet
                    --lfc "${KEA_LFC_EXECUTABLE}"
                    --server "${KEA_DHCP4_EXECUTABLE}"
                    --hook $<TARGET_FILE:kea_db_commands>
                    --mysql-hook "${KEA_MYSQL_HOOK}"
                    --schema "${KEA_MYSQL_SCHEMA}"
                    --mysql-bin "${KEA_MYSQL_CLIENT}"
                    --mysql-install-db "${KEA_MYSQL_INSTALL_DB}"
                    --mysql-server "${KEA_MYSQL_SERVER}"
                    --work-dir ${CMAKE_CURRENT_BINARY_DIR}/mysql-dhcp)
            set_tests_properties(mysql_dhcp PROPERTIES TIMEOUT 240 SKIP_RETURN_CODE 77
                LABELS "MySQL;DHCP"
                ENVIRONMENT "LD_LIBRARY_PATH=${KEA_TEST_LIBRARY_PATH}:$ENV{LD_LIBRARY_PATH}")
        endif()
    endif()
endif()
