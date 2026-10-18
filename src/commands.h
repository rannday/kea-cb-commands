// SPDX-License-Identifier: MPL-2.0
#ifndef KEA_DB_COMMANDS_COMMANDS_H
#define KEA_DB_COMMANDS_COMMANDS_H

namespace isc {
namespace hooks {
class CalloutHandle;
}
} // namespace isc

namespace kea_db_commands {

// Immutable between Kea lifecycle callbacks; commands run on the main thread.
bool mutationsAllowed();

// Synchronous Kea command callouts. Each contains exceptions at the hook boundary.
int diagnostic(isc::hooks::CalloutHandle& handle);
int subnet4List(isc::hooks::CalloutHandle& handle);
int subnet4Get(isc::hooks::CalloutHandle& handle);
int subnet4Del(isc::hooks::CalloutHandle& handle);
int subnet4Set(isc::hooks::CalloutHandle& handle);

int server4List(isc::hooks::CalloutHandle& handle);
int server4Get(isc::hooks::CalloutHandle& handle);
int server4Set(isc::hooks::CalloutHandle& handle);
int server4Del(isc::hooks::CalloutHandle& handle);
int global4List(isc::hooks::CalloutHandle& handle);
int global4Get(isc::hooks::CalloutHandle& handle);
int global4Set(isc::hooks::CalloutHandle& handle);
int global4Del(isc::hooks::CalloutHandle& handle);
int sharedNetwork4List(isc::hooks::CalloutHandle& handle);
int sharedNetwork4Get(isc::hooks::CalloutHandle& handle);
int sharedNetwork4Set(isc::hooks::CalloutHandle& handle);
int sharedNetwork4Del(isc::hooks::CalloutHandle& handle);

int optionDef4List(isc::hooks::CalloutHandle& handle);
int optionDef4Get(isc::hooks::CalloutHandle& handle);
int optionDef4Set(isc::hooks::CalloutHandle& handle);
int optionDef4Del(isc::hooks::CalloutHandle& handle);
int optionGlobal4List(isc::hooks::CalloutHandle& handle);
int optionGlobal4Get(isc::hooks::CalloutHandle& handle);
int optionGlobal4Set(isc::hooks::CalloutHandle& handle);
int optionGlobal4Del(isc::hooks::CalloutHandle& handle);
} // namespace kea_db_commands

#endif
