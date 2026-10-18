// SPDX-License-Identifier: MPL-2.0
#ifndef KEA_DB_COMMANDS_ARGUMENTS_H
#define KEA_DB_COMMANDS_ARGUMENTS_H

#include "command_support.h"

#include <cc/data.h>
#include <dhcpsrv/subnet.h>

namespace kea_db_commands {

// Validate identity selectors before resolving backend state.
void validateLookupArguments(const isc::data::ConstElementPtr& arguments, bool remove);

// Construct the supported minimal native subnet and optional pools.
isc::dhcp::Subnet4Ptr parseSubnet4(const isc::data::ConstElementPtr& input);

} // namespace kea_db_commands

#endif
