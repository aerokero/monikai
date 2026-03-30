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
    "description": "Move towards a specific player.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "player_name": {
                "type": "STRING",
                "description": "Name of the player to move towards."
            },
            "distance": {
                "type": "NUMBER",
                "description": "Stop at this distance from the player (default: 2 blocks)."
            }
        },
        "required": ["player_name"]
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
