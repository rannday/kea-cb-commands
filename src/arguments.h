// SPDX-License-Identifier: MPL-2.0
#ifndef KEA_DB_COMMANDS_ARGUMENTS_H
#define KEA_DB_COMMANDS_ARGUMENTS_H

#include <cc/data.h>
#include <dhcpsrv/subnet.h>
#include <stdexcept>

namespace kea_db_commands {

// Only errors raised by our contract checks may be returned verbatim. Native
// exceptions can contain connection strings and must remain private.
struct ContractError : std::runtime_error {
    using std::runtime_error::runtime_error;
};

// Validate identity selectors before resolving backend state.
void validateLookupArguments(const isc::data::ConstElementPtr& arguments, bool remove);

// Construct the supported minimal native subnet and optional pools.
isc::dhcp::Subnet4Ptr parseSubnet4(const isc::data::ConstElementPtr& input);

} // namespace kea_db_commands

#endif
