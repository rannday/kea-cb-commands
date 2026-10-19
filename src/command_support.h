// SPDX-License-Identifier: MPL-2.0
#ifndef KEA_DB_COMMANDS_COMMAND_SUPPORT_H
#define KEA_DB_COMMANDS_COMMAND_SUPPORT_H

#include "commands.h"

#include <cc/command_interpreter.h>
#include <hooks/callout_handle.h>
#include <initializer_list>
#include <stdexcept>
#include <string>

namespace kea_db_commands {

// Only explicitly constructed contract errors are safe to publish. Native
// exception messages may contain credentials.
struct ContractError : std::runtime_error {
    using std::runtime_error::runtime_error;
};

struct CommandRequest {
    isc::data::ConstElementPtr command;
    isc::data::ConstElementPtr arguments;

    bool acceptsEmptyArguments() const {
        return command && (!arguments || (arguments->getType() == isc::data::Element::map &&
                                          arguments->mapValue().empty()));
    }
};

inline CommandRequest commandRequest(isc::hooks::CalloutHandle& handle) {
    isc::data::ConstElementPtr command;
    handle.getArgument("command", command);
    return {command, command ? command->get("arguments") : isc::data::ConstElementPtr()};
}

// Missing fields remain missing; explicit JSON null is a present value and fails
// a typed check. Callers retain their own schema, messages and validation order.
inline isc::data::ConstElementPtr optionalField(const isc::data::ConstElementPtr& map,
                                                const std::string& name,
                                                isc::data::Element::types type, const char* error) {
    const auto value = map->get(name);
    if (value && value->getType() != type) {
        throw ContractError(error);
    }
    return value;
}

// Required and optional names intentionally share a type; callers specify both
// lists together as the command schema, in that order.
// NOLINTBEGIN(bugprone-easily-swappable-parameters)
inline void requireFields(const isc::data::ConstElementPtr& map,
                          std::initializer_list<const char*> required,
                          std::initializer_list<const char*> optional, const char* error) {
    if (!map || map->getType() != isc::data::Element::map) {
        throw ContractError(error);
    }
    for (const auto* name : required) {
        if (!map->get(name)) {
            throw ContractError(error);
        }
    }
    for (const auto& item : map->mapValue()) {
        bool known = false;
        for (const auto* name : required) {
            known = known || item.first == name;
        }
        for (const auto* name : optional) {
            known = known || item.first == name;
        }
        if (!known) {
            throw ContractError(error);
        }
    }
}

// NOLINTEND(bugprone-easily-swappable-parameters)

inline void requireMutationAdmission() {
    if (!mutationsAllowed()) {
        throw ContractError("Mutations are disabled; configure allow-mutations: true on the "
                            "designated administrative writer.");
    }
}

// Use ConstElementPtr: HookedCommandMgr reads precisely this argument type.
// Publication exceptions remain within each callout's existing outer boundary.
inline int respond(isc::hooks::CalloutHandle& handle, const isc::data::ConstElementPtr& response) {
    handle.setArgument("response", response);
    return 0;
}

// The action constructs its command-specific success/empty envelope. Admission
// stays explicit inside each mutating action, before parsing or backend access.
template <typename Action>
int commandBoundary(isc::hooks::CalloutHandle& handle, const char* native_failure, Action action) {
    using namespace isc::config;
    try {
        isc::data::ConstElementPtr response;
        try {
            response = action();
        } catch (const ContractError& error) {
            response = createAnswer(CONTROL_RESULT_ERROR, error.what());
        } catch (...) {
            response = createAnswer(CONTROL_RESULT_ERROR, native_failure);
        }
        return respond(handle, response);
    } catch (...) {
        return 1;
    }
}

} // namespace kea_db_commands

#endif
