-- test_shield.lua
-- TEST #1: does Hystoria enforce Shield signatures on injected packets?
--
-- What we do:
--   1. Wait for the character to be ready (id + cell known).
--   2. Log our current position.
--   3. Try to find a short-path cell adjacent-ish on the iso grid.
--   4. Inject ONE raw GA0;1 movement packet via bot:move_to().
--      That packet leaves the proxy WITHOUT a Shield signature.
--   5. Wait 3 seconds for the server echo.
--   6. Report:
--        * If `character_moved` fires     -> Shield is NOT enforced. :)
--        * If our cell changes silently   -> also a success signal.
--        * If NOTHING happens             -> Shield is enforced. :(
--   7. Stop the script (we only need ONE test run).
--
-- Run:
--     python -m dofus_bot --proxy --script examples/test_shield.lua
--
-- Safety:
--   * Only injects ONE packet, ever. No loop.
--   * Does nothing if we are in a fight.
--   * Does nothing if no short path is found (fallback: logs "no target").
--   * Uses a distance cap of 6 cells so we never try to cross the map.

local ran = false
local moved = false
local move_data = nil

-- Subscribe early so we don't miss the echo if it comes back fast.
bot:on("character_moved", function(data)
  if ran then
    moved = true
    move_data = data
    bot:log("[TEST#1] character_moved fired: from="
            .. tostring(data.from) .. " to=" .. tostring(data.to)
            .. " (" .. tostring(#data.path - 1) .. " steps)")
  end
end)

bot:on("character_ready", function(info)
  bot:log("[TEST#1] character_ready: id=" .. tostring(info.id)
          .. " name=" .. tostring(info.name))
end)

-- Wait until we are safely in-game, out of combat, with a known cell.
local waited = 0
while not (bot.character.id > 0
           and bot.character.cell >= 0
           and not bot.fight.is_active) do
  if waited == 0 then
    bot:log("[TEST#1] waiting for character_ready + out-of-combat...")
  end
  bot:wait(1)
  waited = waited + 1
  if waited > 60 then
    bot:log("[TEST#1] timeout: not in game after 60s. Aborting.")
    return
  end
end

-- Log the baseline.
local start_cell = bot.character.cell
local map_id = bot.character.map_id
bot:log("[TEST#1] baseline: cell=" .. tostring(start_cell)
        .. " map=" .. tostring(map_id)
        .. " char_id=" .. tostring(bot.character.id))

-- Find a reachable target cell a few tiles away. We iterate over a
-- bunch of iso-grid offsets (1/-1 = same row, 14/-14 and 15/-15 =
-- adjacent rows on a 14-wide losange grid, 28/-28 = two rows down/up)
-- and take the first one whose A* path is short and non-empty.
local offsets = {1, -1, 14, -14, 15, -15, 13, -13, 28, -28, 29, -29}
local target = nil
local path_len = 0
for _, off in ipairs(offsets) do
  local candidate = start_cell + off
  if candidate >= 0 and candidate < 560 then
    local path = bot:path_to(candidate)
    local n = 0
    for _ in pairs(path) do n = n + 1 end  -- lupa table length
    if n >= 2 and n <= 6 then
      target = candidate
      path_len = n
      break
    end
  end
end

if target == nil then
  bot:log("[TEST#1] no short reachable target found from cell "
          .. tostring(start_cell) .. ". Aborting.")
  return
end

bot:log("[TEST#1] target cell = " .. tostring(target)
        .. " (path of " .. tostring(path_len) .. " cells)")
bot:log("[TEST#1] INJECTING unsigned GA0;1 now...")

ran = true
local ok = bot:move_to(target)
if not ok then
  bot:log("[TEST#1] move_to returned false (no path or no id). Aborting.")
  return
end

-- Wait for the server echo. A real walk on an adjacent cell takes
-- ~1 second; give it 5 to be safe.
bot:wait(5)

local end_cell = bot.character.cell
bot:log("[TEST#1] post-wait cell = " .. tostring(end_cell))

if moved then
  bot:log("[TEST#1] >>> VERDICT A: SHIELD OFF <<< "
          .. "Server accepted our unsigned GA0 and echoed character_moved.")
elseif end_cell ~= start_cell then
  bot:log("[TEST#1] >>> VERDICT A (weak): cell changed from "
          .. tostring(start_cell) .. " to " .. tostring(end_cell)
          .. " without a character_moved event. Shield probably OFF.")
else
  bot:log("[TEST#1] >>> VERDICT B/C: SHIELD ON <<< "
          .. "Cell unchanged, no character_moved. The server either "
          .. "dropped the packet silently or rejected it.")
end

bot:log("[TEST#1] Done. Stopping script (no further injections).")
