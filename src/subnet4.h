// SPDX-License-Identifier: MPL-2.0
#ifndef KEA_DB_COMMANDS_SUBNET4_H
#define KEA_DB_COMMANDS_SUBNET4_H

#include <cc/data.h>

namespace kea_db_commands {

// Resolve the current native pool per operation; never retain state across reloads.
// ContractError carries public validation errors; native exception text stays private.
isc::data::ConstElementPtr listSubnets();
isc::data::ConstElementPtr lookupSubnet(const isc::data::ConstElementPtr& arguments, bool remove);
isc::data::ConstElementPtr setSubnet(const isc::data::ConstElementPtr& arguments);

} // namespace kea_db_commands

#endif
