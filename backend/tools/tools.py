write_file_tool = {
    "name": "write_file",
    "description": "Writes content to a file at the specified path. Overwrites if exists.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "path": {
                "type": "STRING",
                "description": "The path of the file to write to."
            },
            "content": {
                "type": "STRING",
                "description": "The content to write to the file."
            }
        },
        "required": ["path", "content"]
    }
}

read_directory_tool = {
    "name": "read_directory",
    "description": "Lists the contents of a directory.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "path": {
                "type": "STRING",
                "description": "The path of the directory to list."
            }
        },
        "required": ["path"]
    }
}

read_file_tool = {
    "name": "read_file",
    "description": "Reads the content of a file.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "path": {
                "type": "STRING",
                "description": "The path of the file to read."
            }
        },
        "required": ["path"]
    }
}

notes_get_tool = {
    "name": "notes_get",
    "description": "Returns the current global notes.md.",
    "parameters": {
        "type": "OBJECT",
        "properties": {}
    }
}

notes_set_tool = {
    "name": "notes_set",
    "description": "Overwrites the global notes.md with the provided content.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "content": {
                "type": "STRING",
                "description": "Full content to write into notes.md."
            }
        },
        "required": ["content"]
    }
}

notes_append_tool = {
    "name": "notes_append",
    "description": "Appends content to the global notes.md.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "content": {
                "type": "STRING",
                "description": "Text to append to notes.md."
            }
        },
        "required": ["content"]
    }
}

tools_list = [{"function_declarations": [
    write_file_tool,
    read_directory_tool,
    read_file_tool,
    notes_get_tool,
    notes_set_tool,
    notes_append_tool
]}]

study_set_fields_tool = {
    "name": "study_set_fields",
    "description": "Updates the Japanese study fields UI (dynamic answer inputs).",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "title": {"type": "STRING", "description": "Optional title for the exercise."},
            "fields": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "key": {"type": "STRING", "description": "Field key/id."},
                        "label": {"type": "STRING", "description": "Field label."},
                        "type": {"type": "STRING", "description": "text | textarea"},
                        "placeholder": {"type": "STRING", "description": "Placeholder text."},
                        "value": {"type": "STRING", "description": "Optional prefill value."}
                    }
                }
            }
        },
        "required": ["fields"]
    }
}

tools_list[0]["function_declarations"].append(study_set_fields_tool)

study_set_page_tool = {
    "name": "study_set_page",
    "description": "Sets the current PDF page in the Japanese study viewer.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "page": {"type": "INTEGER", "description": "1-based page number."}
        },
        "required": ["page"]
    }
}

tools_list[0]["function_declarations"].append(study_set_page_tool)

study_set_notes_tool = {
    "name": "study_set_notes",
    "description": "Updates the study scratchpad notes (replace or append).",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "text": {"type": "STRING", "description": "Notes content to write."},
            "mode": {"type": "STRING", "description": "replace | append"},
            "page_index": {"type": "INTEGER", "description": "Optional scratchpad page index."}
        },
        "required": ["text"]
    }
}

tools_list[0]["function_declarations"].append(study_set_notes_tool)

# ====================================
# Minecraft Tools
# ====================================

minecraft_chat_message_tool = {
    "name": "minecraft_chat_message",
    "description": "Send a message in Minecraft chat. Use this to communicate with players or send commands.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "message": {
                "type": "STRING",
                "description": "The message to send in chat."
            }
        },
        "required": ["message"]
    }
}

tools_list[0]["function_declarations"].append(minecraft_chat_message_tool)

minecraft_move_to_player_tool = {
    "name": "minecraft_move_to_player",
    "description": "Move towards a player. If player name is not specified, will follow the only available player (or closest if multiple exist).",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "player_name": {
                "type": "STRING",
                "description": "Name of the player to move towards. If not provided, will auto-select the only available player or follow the closest one."
            },
            "distance": {
                "type": "NUMBER",
                "description": "Stop at this distance from the player (default: 2 blocks)."
            }
        },
        "required": []
    }
}

tools_list[0]["function_declarations"].append(minecraft_move_to_player_tool)

minecraft_break_block_tool = {
    "name": "minecraft_break_block",
    "description": "Break a block at specified coordinates.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "x": {
                "type": "NUMBER",
                "description": "X coordinate"
            },
            "y": {
                "type": "NUMBER",
                "description": "Y coordinate"
            },
            "z": {
                "type": "NUMBER",
                "description": "Z coordinate"
            }
        },
        "required": ["x", "y", "z"]
    }
}

tools_list[0]["function_declarations"].append(minecraft_break_block_tool)

minecraft_inventory_status_tool = {
    "name": "minecraft_inventory_status",
    "description": "Get current inventory items and player status (health, hunger, position).",
    "parameters": {
        "type": "OBJECT",
        "properties": {}
    }
}

tools_list[0]["function_declarations"].append(minecraft_inventory_status_tool)

minecraft_respawn_tool = {
    "name": "minecraft_respawn",
    "description": "Respawn the bot if it is dead.",
    "parameters": {
        "type": "OBJECT",
        "properties": {}
    }
}

tools_list[0]["function_declarations"].append(minecraft_respawn_tool)

minecraft_move_to_position_tool = {
    "name": "minecraft_move_to_position",
    "description": "Move to specific coordinates.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "x": {
                "type": "NUMBER",
                "description": "Target X coordinate"
            },
            "y": {
                "type": "NUMBER",
                "description": "Target Y coordinate"
            },
            "z": {
                "type": "NUMBER",
                "description": "Target Z coordinate"
            },
            "range": {
                "type": "NUMBER",
                "description": "Stop at this distance (default: 1 block)"
            }
        },
        "required": ["x", "y", "z"]
    }
}

tools_list[0]["function_declarations"].append(minecraft_move_to_position_tool)

minecraft_drop_item_tool = {
    "name": "minecraft_drop_item",
    "description": "Drop an item from inventory.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "item_name": {
                "type": "STRING",
                "description": "Name of the item to drop (e.g. 'oak_log', 'dirt')"
            },
            "count": {
                "type": "NUMBER",
                "description": "Number of items to drop (default: 1)"
            }
        },
        "required": ["item_name"]
    }
}

tools_list[0]["function_declarations"].append(minecraft_drop_item_tool)

# --- Faza 3: Advanced Minecraft Tools ---

minecraft_mine_ore_tool = {
    "name": "minecraft_mine_ore",
    "description": "Find and mine nearby ore blocks. Useful for resource gathering.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "ore_type": {
                "type": "STRING",
                "description": "Type of ore to mine: stone, iron, coal, diamond, copper, gold"
            },
            "max_blocks": {
                "type": "INTEGER",
                "description": "Maximum blocks to mine (default: 5, max: 20)"
            },
            "max_distance": {
                "type": "INTEGER",
                "description": "Maximum distance to search for ore (default: 50)"
            }
        },
        "required": ["ore_type"]
    }
}
tools_list[0]["function_declarations"].append(minecraft_mine_ore_tool)

minecraft_craft_recipe_tool = {
    "name": "minecraft_craft_recipe",
    "description": "Craft items using recipes. Check inventory for ingredients first.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "recipe": {
                "type": "STRING",
                "description": "Recipe name: sticks, planks, charcoal, etc"
            },
            "count": {
                "type": "INTEGER",
                "description": "Number of items to craft (default: 1, max: 64)"
            }
        },
        "required": ["recipe"]
    }
}
tools_list[0]["function_declarations"].append(minecraft_craft_recipe_tool)

minecraft_hunt_mobs_tool = {
    "name": "minecraft_hunt_mobs",
    "description": "Find and attack nearby hostile mobs. Combat action - bot will attack until mob dies or health gets low.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "mob_type": {
                "type": "STRING",
                "description": "Type of mob: zombie, spider, creeper, skeleton, enderman, etc"
            },
            "max_distance": {
                "type": "INTEGER",
                "description": "Maximum distance to search (default: 50)"
            },
            "max_health_loss": {
                "type": "INTEGER",
                "description": "Retreat if health drops by this much (default: 5)"
            }
        },
        "required": ["mob_type"]
    }
}
tools_list[0]["function_declarations"].append(minecraft_hunt_mobs_tool)

minecraft_navigate_to_location_tool = {
    "name": "minecraft_navigate_to_location",
    "description": "Navigate to a specific location (x, y, z coordinates). Bot will pathfind and climb as needed.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "x": {
                "type": "NUMBER",
                "description": "Target X coordinate"
            },
            "y": {
                "type": "NUMBER",
                "description": "Target Y coordinate"
            },
            "z": {
                "type": "NUMBER",
                "description": "Target Z coordinate"
            },
            "label": {
                "type": "STRING",
                "description": "Optional location name for logging (e.g., 'Spawn', 'Base')"
            }
        },
        "required": ["x", "y", "z"]
    }
}
tools_list[0]["function_declarations"].append(minecraft_navigate_to_location_tool)

minecraft_connect_to_server_tool = {
    "name": "minecraft_connect_to_server",
    "description": "Connect to a Minecraft server with specified host and port. Disconnects from current server and connects to the new one.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "host": {
                "type": "STRING",
                "description": "The server hostname or IP address (e.g., 'localhost', 'play.example.com', '192.168.1.100')"
            },
            "port": {
                "type": "NUMBER",
                "description": "The server port number (default: 25565 for Minecraft)"
            }
        },
        "required": ["host", "port"]
    }
}
tools_list[0]["function_declarations"].append(minecraft_connect_to_server_tool)

# --- AIRI parity tools (extended action surface) ---

minecraft_skip_tool = {
    "name": "minecraft_skip",
    "description": "Skip this turn without performing any world action.",
    "parameters": {
        "type": "OBJECT",
        "properties": {}
    }
}
tools_list[0]["function_declarations"].append(minecraft_skip_tool)

minecraft_stop_actions_tool = {
    "name": "minecraft_stop_actions",
    "description": "Force stop currently running Minecraft actions.",
    "parameters": {
        "type": "OBJECT",
        "properties": {}
    }
}
tools_list[0]["function_declarations"].append(minecraft_stop_actions_tool)

minecraft_give_up_tool = {
    "name": "minecraft_give_up",
    "description": "Report that the bot is currently stuck and provide reason.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "reason": {
                "type": "STRING",
                "description": "Short reason why the bot is stuck"
            }
        },
        "required": ["reason"]
    }
}
tools_list[0]["function_declarations"].append(minecraft_give_up_tool)

minecraft_give_player_tool = {
    "name": "minecraft_give_player",
    "description": "Give an item to a player.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "player_name": {"type": "STRING", "description": "Target player name"},
            "item_name": {"type": "STRING", "description": "Item name"},
            "count": {"type": "INTEGER", "description": "Amount to give"}
        },
        "required": ["player_name", "item_name"]
    }
}
tools_list[0]["function_declarations"].append(minecraft_give_player_tool)

minecraft_consume_tool = {
    "name": "minecraft_consume",
    "description": "Eat or drink an item.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "item_name": {"type": "STRING", "description": "Food/drink item name"}
        },
        "required": ["item_name"]
    }
}
tools_list[0]["function_declarations"].append(minecraft_consume_tool)

minecraft_equip_tool = {
    "name": "minecraft_equip",
    "description": "Equip an item from inventory. Armor items are automatically equipped to the correct slot (helmet→head, chestplate→torso, leggings→legs, boots→feet, shield→off-hand).",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "item_name": {"type": "STRING", "description": "Item to equip"}
        },
        "required": ["item_name"]
    }
}
tools_list[0]["function_declarations"].append(minecraft_equip_tool)

minecraft_equip_armor_tool = {
    "name": "minecraft_equip_armor",
    "description": "Automatically equip the best available armor from your inventory to the correct armor slots (head, chest, legs, feet). Armor is prioritized by protection level. Call this whenever you pick up armor or want to gear up.",
    "parameters": {
        "type": "OBJECT",
        "properties": {},
        "required": []
    }
}
tools_list[0]["function_declarations"].append(minecraft_equip_armor_tool)

minecraft_put_in_chest_tool = {
    "name": "minecraft_put_in_chest",
    "description": "Put items into nearest chest.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "item_name": {"type": "STRING", "description": "Item name"},
            "count": {"type": "INTEGER", "description": "Amount to store"}
        },
        "required": ["item_name", "count"]
    }
}
tools_list[0]["function_declarations"].append(minecraft_put_in_chest_tool)

minecraft_take_from_chest_tool = {
    "name": "minecraft_take_from_chest",
    "description": "Take items from nearest chest.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "item_name": {"type": "STRING", "description": "Item name"},
            "count": {"type": "INTEGER", "description": "Amount to take"}
        },
        "required": ["item_name", "count"]
    }
}
tools_list[0]["function_declarations"].append(minecraft_take_from_chest_tool)

minecraft_discard_tool = {
    "name": "minecraft_discard",
    "description": "Discard items from inventory.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "item_name": {"type": "STRING", "description": "Item name"},
            "count": {"type": "INTEGER", "description": "Amount to discard"}
        },
        "required": ["item_name", "count"]
    }
}
tools_list[0]["function_declarations"].append(minecraft_discard_tool)

minecraft_collect_blocks_tool = {
    "name": "minecraft_collect_blocks",
    "description": "Collect nearest blocks of a given type.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "block_type": {"type": "STRING", "description": "Block type to collect"},
            "count": {"type": "INTEGER", "description": "How many blocks to collect"}
        },
        "required": ["block_type", "count"]
    }
}
tools_list[0]["function_declarations"].append(minecraft_collect_blocks_tool)

minecraft_mine_block_at_tool = {
    "name": "minecraft_mine_block_at",
    "description": "Mine a block at exact coordinates.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "x": {"type": "NUMBER", "description": "X coordinate"},
            "y": {"type": "NUMBER", "description": "Y coordinate"},
            "z": {"type": "NUMBER", "description": "Z coordinate"},
            "expected_block_type": {"type": "STRING", "description": "Optional expected block type"}
        },
        "required": ["x", "y", "z"]
    }
}
tools_list[0]["function_declarations"].append(minecraft_mine_block_at_tool)

minecraft_smelt_item_tool = {
    "name": "minecraft_smelt_item",
    "description": "Smelt item in nearest furnace.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "item_name": {"type": "STRING", "description": "Input item name"},
            "count": {"type": "INTEGER", "description": "How many times to smelt"}
        },
        "required": ["item_name", "count"]
    }
}
tools_list[0]["function_declarations"].append(minecraft_smelt_item_tool)

minecraft_clear_furnace_tool = {
    "name": "minecraft_clear_furnace",
    "description": "Clear nearest furnace output/input slots.",
    "parameters": {
        "type": "OBJECT",
        "properties": {}
    }
}
tools_list[0]["function_declarations"].append(minecraft_clear_furnace_tool)

minecraft_place_here_tool = {
    "name": "minecraft_place_here",
    "description": "Place a block near current bot position.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "block_type": {"type": "STRING", "description": "Block type to place"}
        },
        "required": ["block_type"]
    }
}
tools_list[0]["function_declarations"].append(minecraft_place_here_tool)

minecraft_attack_tool = {
    "name": "minecraft_attack",
    "description": "Attack nearest entity of a given type.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "entity_type": {"type": "STRING", "description": "Entity type"}
        },
        "required": ["entity_type"]
    }
}
tools_list[0]["function_declarations"].append(minecraft_attack_tool)

minecraft_attack_player_tool = {
    "name": "minecraft_attack_player",
    "description": "Attack a specific player.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "player_name": {"type": "STRING", "description": "Target player"}
        },
        "required": ["player_name"]
    }
}
tools_list[0]["function_declarations"].append(minecraft_attack_player_tool)

minecraft_go_to_bed_tool = {
    "name": "minecraft_go_to_bed",
    "description": "Go to nearest bed and sleep.",
    "parameters": {
        "type": "OBJECT",
        "properties": {}
    }
}
tools_list[0]["function_declarations"].append(minecraft_go_to_bed_tool)

minecraft_activate_tool = {
    "name": "minecraft_activate",
    "description": "Activate nearest interactable block of given type.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "target_type": {"type": "STRING", "description": "Type such as furnace, chest, bed, door"}
        },
        "required": ["target_type"]
    }
}
tools_list[0]["function_declarations"].append(minecraft_activate_tool)

minecraft_recipe_plan_tool = {
    "name": "minecraft_recipe_plan",
    "description": "Plan recipe requirements for crafting.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "item_name": {"type": "STRING", "description": "Recipe output item"},
            "amount": {"type": "INTEGER", "description": "Desired amount"}
        },
        "required": ["item_name"]
    }
}
tools_list[0]["function_declarations"].append(minecraft_recipe_plan_tool)

minecraft_scan_nearby_tool = {
    "name": "minecraft_scan_nearby",
    "description": "Scan the nearby area for interesting things to notice or explore. Returns entities (mobs, players), ores, water, lava, caves, and other notable features. Useful for understanding what's around you and making decisions about what to investigate.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "range": {"type": "INTEGER", "description": "Search radius in blocks (10-100, default 50)"}
        },
        "required": []
    }
}
tools_list[0]["function_declarations"].append(minecraft_scan_nearby_tool)

minecraft_use_action_tool = {
    "name": "minecraft_use_action",
    "description": "Execute any raw Minecraft action name with JSON params for maximum compatibility.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "Raw action name"},
            "params": {"type": "OBJECT", "description": "Raw action params"}
        },
        "required": ["action"]
    }
}
tools_list[0]["function_declarations"].append(minecraft_use_action_tool)

# --- Calendar Tools ---
create_event_tool = {
    "name": "create_event",
    "description": "Creates a new event in the calendar. For all-day and multi-day events, set all_day=true and use an exclusive end date: an event advertised as 2026-05-15 to 2026-05-17 must use start_iso='2026-05-15T00:00:00' and end_iso='2026-05-18T00:00:00'. For timed events, use specific times.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "summary": {"type": "STRING", "description": "The title or summary of the event."},
            "start_iso": {"type": "STRING", "description": "The start time in ISO 8601 format (e.g., '2026-05-01T00:00:00' for all-day on May 1st)."},
            "end_iso": {"type": "STRING", "description": "The exclusive end time in ISO 8601 format. For all-day events, use midnight on the day after the last included day."},
            "description": {"type": "STRING", "description": "An optional longer description for the event."},
            "all_day": {"type": "BOOLEAN", "description": "Set to true for all-day events (default: false)."},
        },
        "required": ["summary", "start_iso", "end_iso"],
    },
}
tools_list[0]["function_declarations"].append(create_event_tool)

list_events_tool = {
    "name": "list_events",
    "description": "Lists events from the calendar within a specified time range.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "start_range_iso": {"type": "STRING", "description": "The start of the time range in ISO 8601 format."},
            "end_range_iso": {"type": "STRING", "description": "The end of the time range in ISO 8601 format."},
        },
        "required": ["start_range_iso", "end_range_iso"],
    },
}
tools_list[0]["function_declarations"].append(list_events_tool)

delete_event_tool = {
    "name": "delete_event",
    "description": "Deletes an event from the calendar by its ID.",
    "parameters": {"type": "OBJECT", "properties": {"event_id": {"type": "STRING", "description": "The unique ID of the event to delete."}}, "required": ["event_id"]},
}
tools_list[0]["function_declarations"].append(delete_event_tool)

update_event_tool = {
    "name": "update_event",
    "description": "Updates an existing event in the calendar (e.g., change summary/name). Provide the event ID and the new summary.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "event_id": {"type": "STRING", "description": "The unique ID of the event to update."},
            "summary": {"type": "STRING", "description": "The new summary/title for the event."},
        },
        "required": ["event_id", "summary"],
    },
}
tools_list[0]["function_declarations"].append(update_event_tool)
