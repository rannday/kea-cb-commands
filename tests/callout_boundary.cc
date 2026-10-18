// SPDX-License-Identifier: MPL-2.0
#include <config.h>

#include "../src/command_support.h"
#include "../src/subnet4.h"

#include <hooks/callout_manager.h>
#include <iostream>

namespace {
bool allow_mutations = false;
bool contract_error = false;
unsigned backend_calls = 0;

isc::data::ConstElementPtr backendFailure() {
    ++backend_calls;
    if (contract_error) {
        throw kea_db_commands::ContractError("Public validation failure.");
    }
    throw std::runtime_error("PRIVATE native backend connection details");
}

void check(bool condition, const char* message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

using Callout = int (*)(isc::hooks::CalloutHandle&);

void expect(Callout callout, const char* text, bool malformed_handle = false) {
    auto manager = boost::shared_ptr<isc::hooks::CalloutManager>(new isc::hooks::CalloutManager(0));
    isc::hooks::CalloutHandle handle(manager);
    if (malformed_handle) {
        handle.setArgument("command", 42);
    } else {
        isc::data::ConstElementPtr command =
            isc::data::Element::fromJSON(R"({"command":"fixture","arguments":{}})");
        handle.setArgument("command", command);
    }
    check(callout(handle) == 0, "Exception escaped the callout response boundary.");
    isc::data::ConstElementPtr response;
    handle.getArgument("response", response);
    check(response && response->mapValue().size() == 2, "Response envelope changed.");
    check(response->get("result")->intValue() == 1, "Expected an error result.");
    check(response->get("text")->stringValue() == text, "Public error text changed.");
}
} // namespace

// Link the actual production callouts to deterministic failing backend fixtures.
// No database is opened, stopped or modified by this test.
namespace kea_db_commands {
bool mutationsAllowed() {
    return allow_mutations;
}
isc::data::ConstElementPtr listSubnets() {
    return backendFailure();
}
isc::data::ConstElementPtr lookupSubnet(const isc::data::ConstElementPtr&, bool) {
    return backendFailure();
}
isc::data::ConstElementPtr setSubnet(const isc::data::ConstElementPtr&) {
    return backendFailure();
}
} // namespace kea_db_commands

int main() {
    using namespace kea_db_commands;
    try {
        const char* denied = "Mutations are disabled; configure allow-mutations: true on the "
                             "designated administrative writer.";
        expect(subnet4Set, denied);
        expect(subnet4Del, denied);
        check(backend_calls == 0, "Denied mutations reached the backend.");

        allow_mutations = true;
        expect(subnet4List, "Configuration backend read failed or unavailable.");
        expect(subnet4Get, "Configuration backend read failed or unavailable.");
        expect(subnet4Set, "Configuration backend write failed or unavailable; reconcile "
                           "backend state before retrying.");
        expect(subnet4Del, "Configuration backend deletion failed or unavailable; reconcile "
                           "backend state before retrying.");
        check(backend_calls == 4, "Unexpected retry or missing backend invocation.");

        contract_error = true;
        for (const auto callout : {subnet4List, subnet4Get, subnet4Set, subnet4Del}) {
            expect(callout, "Public validation failure.");
        }
        expect(diagnostic, "Configuration backend diagnostic failed.", true);
        expect(subnet4List, "Configuration backend read failed or unavailable.", true);
        expect(subnet4Get, "Configuration backend read failed or unavailable.", true);
        expect(subnet4Set,
               "Configuration backend write failed or unavailable; reconcile "
               "backend state before retrying.",
               true);
        expect(subnet4Del,
               "Configuration backend deletion failed or unavailable; reconcile "
               "backend state before retrying.",
               true);
        std::cout << "PASS: actual callout exception envelopes, private native errors, "
                     "admission and no retries\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << error.what() << '\n';
        return 1;
    }
}
