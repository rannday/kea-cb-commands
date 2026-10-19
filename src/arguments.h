// SPDX-License-Identifier: MPL-2.0
#ifndef KEA_DB_COMMANDS_ARGUMENTS_H
#define KEA_DB_COMMANDS_ARGUMENTS_H

#include <config.h>

#include <cc/data.h>
#include <dhcpsrv/subnet.h>

namespace kea_db_commands {

// Validate identity selectors before resolving backend state.
void validateLookupArguments(const isc::data::ConstElementPtr& arguments, bool remove);

// Construct only the explicitly supported SQL-backed native attributes.
isc::dhcp::Subnet4Ptr parseSubnet4(const isc::data::ConstElementPtr& input);

// Validate the complete native view against the supported subset, then preserve
// omitted supported attributes. Refuse dependency-bearing objects and rich pool
// replacement rather than silently dropping their configuration.
isc::dhcp::Subnet4Ptr preserveSubnet4(const isc::data::ConstElementPtr& input,
                                      const isc::dhcp::Subnet4Ptr& existing);

} // namespace kea_db_commands

#endif
