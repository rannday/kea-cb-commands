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
    #include <dhcpsrv/config_backend_dhcp4_mgr.h>
    static_assert(KEA_HOOKS_VERSION == 30201 || KEA_HOOKS_VERSION == 30004,
                  "Only Kea 3.2.1 and 3.0.4 have been source-assessed");
    int main() {
        auto pool = isc::dhcp::ConfigBackendDHCPv4Mgr::instance().getPool();
        return pool ? 0 : 1;
    }
]=] KEA_DB_COMMANDS_API_LINKS)
unset(CMAKE_REQUIRED_LIBRARIES)
if(NOT KEA_DB_COMMANDS_API_LINKS)
    message(FATAL_ERROR "Required Kea headers/API do not compile and link. See CMakeFiles/CMakeConfigureLog.yaml or CMakeError.log.")
endif()

add_library(kea_db_commands MODULE src/diagnostic.cc)
set_target_properties(kea_db_commands PROPERTIES
    OUTPUT_NAME dhcp_db_commands
    CXX_VISIBILITY_PRESET hidden
    VISIBILITY_INLINES_HIDDEN YES)
target_link_libraries(kea_db_commands PRIVATE PkgConfig::KEA)
target_compile_options(kea_db_commands PRIVATE -Wall -Wextra -Wpedantic)
target_link_options(kea_db_commands PRIVATE -Wl,-z,defs)

include(GNUInstallDirs)
install(TARGETS kea_db_commands LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}/kea/hooks)

include(CTest)
if(BUILD_TESTING)
    find_package(Python3 REQUIRED COMPONENTS Interpreter)
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
        set_tests_properties(hook_lifecycle PROPERTIES TIMEOUT 90)
    endif()
endif()
