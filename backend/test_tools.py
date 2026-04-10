from backend.tools import tools_list
decls = tools_list[0].get('function_declarations', [])
minecraft = [d for d in decls if 'minecraft' in d.get('name', '')]
print(f'Total tools: {len(decls)}')
print(f'Minecraft tools: {len(minecraft)}')
for t in minecraft:
    print(f'  - {t.get("name")}')
