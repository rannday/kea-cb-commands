// SPDX-License-Identifier: MPL-2.0
#include <config.h>

#include "backend_support.h"
#include "commands.h"

#include <asiolink/io_address.h>
#include <cc/command_interpreter.h>
#include <cc/stamped_value.h>
#include <cmath>
#include <cstdint>
#include <database/server.h>
#include <dhcpsrv/cfgmgr.h>
#include <dhcpsrv/config_backend_dhcp4_mgr.h>
#include <limits>
#include <map>

namespace kea_db_commands {
namespace {
using namespace isc::data;
using namespace isc::db;
using namespace isc::dhcp;
using namespace isc::config;

BackendSelector selectedBackend(const bool available) {
    return singleBackendSelector(available, CfgMgr::instance().getCurrentCfg(),
                                 "Exactly one SQL configuration backend is required.",
                                 "Exactly one SQL configuration backend is required.",
                                 "A PostgreSQL or MySQL configuration backend is required.");
}

ServerTag tagArgument(const ConstElementPtr& arguments, const bool record) {
    const auto value =
        optionalField(arguments, "server-tag", Element::string, "server-tag must be a string.");
    if (!value) {
        throw ContractError("server-tag is required.");
    }
    if (value->stringValue().find('\0') != std::string::npos) {
        throw ContractError("server-tag cannot contain NUL.");
    }
    const auto tag = validatedServerTag(value->stringValue());
    if (tag.get() == "any" || (record && tag.amAll())) {
        throw ContractError("Reserved server-tag cannot identify a server record.");
    }
    return tag;
}

ElementPtr countResult(const int64_t count) {
    auto result = Element::createMap();
    result->set("count", Element::create(count));
    return result;
}

enum class Operation : std::uint8_t { List, Get, Set, Del };

int serverCommand(isc::hooks::CalloutHandle& handle, const Operation operation) {
    return commandBoundary(
        handle,
        "Configuration backend operation failed; reconcile persisted state before retrying.",
        [&]() -> ConstElementPtr {
            if (operation == Operation::Set || operation == Operation::Del) {
                requireMutationAdmission();
            }
            const auto request = commandRequest(handle);
            if (operation == Operation::List) {
                if (!request.acceptsEmptyArguments()) {
                    throw ContractError("cb-server4-list accepts only absent or empty arguments.");
                }
            } else if (operation == Operation::Set) {
                requireFields(request.arguments, {"server-tag", "description"}, {},
                              "Expected only server-tag and description.");
            } else {
                requireFields(request.arguments, {"server-tag"}, {}, "Expected only server-tag.");
            }
            const auto pool = backendPool<ConfigBackendDHCPv4Mgr>();
            const auto backend = selectedBackend(bool(pool));
            auto rows = Element::createList();
            if (operation == Operation::List) {
                const auto servers = pool->getAllServers4(backend);
                std::map<std::string, ServerPtr> sorted;
                for (const auto& server : servers) {
                    sorted.emplace(server->getServerTagAsText(), server);
                }
                for (const auto& server : sorted) {
                    rows->add(server.second->toElement());
                }
            } else {
                const auto tag = tagArgument(request.arguments, true);
                if (operation == Operation::Set) {
                    const auto description =
                        optionalField(request.arguments, "description", Element::string,
                                      "description must be a string.");
                    if (description->stringValue().size() > 65536 ||
                        description->stringValue().find('\0') != std::string::npos) {
                        throw ContractError("description exceeds 65536 bytes or contains NUL.");
                    }
                    const auto server = Server::create(tag, description->stringValue());
                    pool->createUpdateServer4(backend, server);
                }
                const auto server = pool->getServer4(backend, tag);
                if (operation == Operation::Del && server) {
                    // Both native drivers purge unrelated orphan globals/options/definitions.
                    // Native collection APIs cannot prove that those orphan sets are empty.
                    throw ContractError("Server deletion is unsupported: native orphan cleanup "
                                        "cannot be verified safe.");
                }
                if (server) {
                    rows->add(server->toElement());
                }
            }
            auto result = countResult(static_cast<int64_t>(rows->size()));
            result->set("servers", rows);
            if (operation == Operation::Set || operation == Operation::Del) {
                result->set("activation-requested", Element::create(false));
            }
            const bool found = rows->size() != 0;
            return createAnswer(found ? CONTROL_RESULT_SUCCESS : CONTROL_RESULT_EMPTY,
                                found ? "DHCPv4 server records retrieved."
                                      : "DHCPv4 server record not found.",
                                result);
        });
}

// Deliberately bounded scalar contract; compound/dotted names require separate
// native encoding and semantic validation. This is not commercial parity.
const std::map<std::string, Element::types> globalTypes = {
    {"valid-lifetime", Element::integer},
    {"min-valid-lifetime", Element::integer},
    {"max-valid-lifetime", Element::integer},
    {"renew-timer", Element::integer},
    {"rebind-timer", Element::integer},
    {"decline-probation-period", Element::integer},
    {"echo-client-id", Element::boolean},
    {"match-client-id", Element::boolean},
    {"authoritative", Element::boolean},
    {"calculate-tee-times", Element::boolean},
    {"t1-percent", Element::real},
    {"t2-percent", Element::real},
    {"next-server", Element::string},
    {"server-hostname", Element::string},
    {"boot-file-name", Element::string}};

void validateGlobal(const std::string& name, const ConstElementPtr& value) {
    const auto type = globalTypes.find(name);
    if (type == globalTypes.end()) {
        throw ContractError("Unsupported global parameter name.");
    }
    if (!value) {
        return;
    }
    if (value->getType() != type->second) {
        throw ContractError("Incorrect global parameter value type.");
    }
    if (type->second == Element::integer &&
        (value->intValue() < 0 ||
         static_cast<uint64_t>(value->intValue()) > std::numeric_limits<uint32_t>::max() ||
         (name.find("valid-lifetime") != std::string::npos && value->intValue() == 0))) {
        throw ContractError(
            "Global timer must be an unsigned 32-bit value; lifetimes must be positive.");
    }
    if (type->second == Element::real && (!std::isfinite(value->doubleValue()) ||
                                          value->doubleValue() <= 0 || value->doubleValue() >= 1)) {
        throw ContractError("Global percentage must be finite and strictly between zero and one.");
    }
    if (type->second == Element::string) {
        const auto text = value->stringValue();
        const size_t limit = name == "boot-file-name" ? 127 : 63;
        if (text.find('\0') != std::string::npos || text.size() > limit) {
            throw ContractError("Global string contains NUL or exceeds its supported DHCP field.");
        }
        if (name == "next-server") {
            try {
                if (!isc::asiolink::IOAddress(text).isV4()) {
                    throw ContractError("next-server must be an IPv4 address.");
                }
            } catch (const ContractError&) {
                throw;
            } catch (...) {
                throw ContractError("next-server must be an IPv4 address.");
            }
        }
    }
}

ElementPtr parameterRow(const StampedValuePtr& value) {
    auto row = Element::createMap();
    row->set("name", Element::create(value->getName()));
    row->set("value", value->getElementValue());
    auto tags = Element::createList();
    for (const auto& tag : value->getServerTags()) {
        tags->add(Element::create(tag.get()));
    }
    row->set("server-tags", tags);
    return row;
}

int globalCommand(isc::hooks::CalloutHandle& handle, const Operation operation) {
    return commandBoundary(
        handle,
        "Configuration backend operation failed; reconcile persisted state before retrying.",
        [&]() -> ConstElementPtr {
            if (operation == Operation::Set || operation == Operation::Del) {
                requireMutationAdmission();
            }
            const auto arguments = commandRequest(handle).arguments;
            if (operation == Operation::List) {
                requireFields(arguments, {"server-tag"}, {}, "Expected only server-tag.");
            } else if (operation == Operation::Set) {
                requireFields(arguments, {"server-tag", "name", "value"}, {},
                              "Expected only server-tag, name and value.");
            } else {
                requireFields(arguments, {"server-tag", "name"}, {},
                              "Expected only server-tag and name.");
            }
            const auto tag = tagArgument(arguments, false);
            std::string name;
            ConstElementPtr value;
            if (operation != Operation::List) {
                const auto field =
                    optionalField(arguments, "name", Element::string, "name must be a string.");
                name = field->stringValue();
                value = operation == Operation::Set ? arguments->get("value") : ConstElementPtr();
                validateGlobal(name, value);
            }
            const auto pool = backendPool<ConfigBackendDHCPv4Mgr>();
            const auto backend = selectedBackend(bool(pool));
            const auto selector = serverSelector(tag);
            if (!tag.amAll() && !pool->getServer4(backend, tag)) {
                throw ContractError("server-tag must already exist in the configuration backend.");
            }
            auto rows = Element::createList();
            int64_t deleted = 0;
            if (operation == Operation::List) {
                const auto values = pool->getAllGlobalParameters4(backend, selector);
                std::map<std::string, StampedValuePtr> sorted;
                for (const auto& entry : values) {
                    // Preserve native observations, including unsupported names/types.
                    // Never silently collapse distinct associations.
                    if (!sorted.emplace(entry->getName(), entry).second) {
                        throw ContractError("Ambiguous global parameter view.");
                    }
                }
                for (const auto& entry : sorted) {
                    rows->add(parameterRow(entry.second));
                }
            } else {
                if (operation == Operation::Set || operation == Operation::Del) {
                    // Native reads filter/collapse associations. Native update/delete
                    // affect whole rows, so even an apparently exclusive value may
                    // belong to another server. Do not mutate an existing value.
                    const auto existing = pool->getGlobalParameter4(backend, selector, name);
                    if (existing) {
                        throw ContractError(
                            "Global mutation is unsupported for existing values: native "
                            "readback cannot verify complete associations.");
                    }
                    if (operation == Operation::Set) {
                        // An empty selected view excludes both an exact row and
                        // common fallback. Native insert attaches only this tag.
                        pool->createUpdateGlobalParameter4(
                            backend, selector,
                            StampedValue::create(name, Element::fromJSON(value->str())));
                    }
                    // Missing delete is read-only: native no-op deletion creates
                    // an audit revision and is deliberately not invoked.
                }
                if (operation != Operation::Del) {
                    const auto stored = pool->getGlobalParameter4(backend, selector, name);
                    if (stored) {
                        rows->add(parameterRow(stored));
                    }
                }
            }
            auto result = countResult(
                operation == Operation::Del ? deleted : static_cast<int64_t>(rows->size()));
            result->set("parameters", rows);
            result->set("server-tag", Element::create(tag.get()));
            if (operation == Operation::Set || operation == Operation::Del) {
                result->set("activation-requested", Element::create(false));
            }
            return createAnswer(result->get("count")->intValue() ? CONTROL_RESULT_SUCCESS
                                                                 : CONTROL_RESULT_EMPTY,
                                "DHCPv4 global parameter operation completed.", result);
        });
}
} // namespace

int server4List(isc::hooks::CalloutHandle& handle) {
    return serverCommand(handle, Operation::List);
}
int server4Get(isc::hooks::CalloutHandle& handle) {
    return serverCommand(handle, Operation::Get);
}
int server4Set(isc::hooks::CalloutHandle& handle) {
    return serverCommand(handle, Operation::Set);
}
int server4Del(isc::hooks::CalloutHandle& handle) {
    return serverCommand(handle, Operation::Del);
}
int global4List(isc::hooks::CalloutHandle& handle) {
    return globalCommand(handle, Operation::List);
}
int global4Get(isc::hooks::CalloutHandle& handle) {
    return globalCommand(handle, Operation::Get);
}
int global4Set(isc::hooks::CalloutHandle& handle) {
    return globalCommand(handle, Operation::Set);
}
int global4Del(isc::hooks::CalloutHandle& handle) {
    return globalCommand(handle, Operation::Del);
}
} // namespace kea_db_commands
