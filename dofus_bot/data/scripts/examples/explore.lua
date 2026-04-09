-- explore.lua
-- Drive the character around the current map using the pathfinder.
-- Demonstrates every movement primitive added in iteration 3:
--   bot:path_to, bot:move_to, bot:move_to_xy, bot:distance,
--   bot:block_cells, bot:set_map_size, and the character_moved event.
--
-- Run with:
--     python -m dofus_bot --proxy --script examples/explore.lua
--
-- Safety note
-- -----------
-- The bot only walks AFTER the server has told us who we are
-- (character_ready event). Before that, bot.character.id is 0 and
-- move_to refuses to inject anything.

local waypoints = {
  {x = 3,  y = 5},
  {x = 10, y = 5},
  {x = 10, y = 15},
  {x = 3,  y = 15},
}

local index = 1
local ready = false

bot:on("character_ready", function(info)
  ready = true
  bot:log("character_ready: id=" .. tostring(info.id)
          .. " name=" .. tostring(info.name))
end)

bot:on("character_moved", function(data)
  bot:log("moved: " .. tostring(data.from) .. " -> " .. tostring(data.to)
          .. " (" .. tostring(#data.path - 1) .. " steps)")
end)

bot:on("map_change", function(data)
  -- New map, restart the loop from the first waypoint. If a given
  -- map has a non-standard size, override it here:
  --     bot:set_map_size(15, 17)
  index = 1
  bot:log("map_change -> " .. tostring(data.map_id))
end)

-- Main loop: walk the waypoint rectangle forever.
while true do
  if ready and not bot.fight.is_active and bot.character.cell >= 0 then
    local wp = waypoints[index]
    bot:log("walking to (" .. wp.x .. ", " .. wp.y .. ")")
    if bot:move_to_xy(wp.x, wp.y) then
      -- Rough wait: 1 tile/sec is generous for a 14x40 map.
      bot:wait(6)
    else
      bot:log("move_to_xy failed (no path or no char id yet)")
      bot:wait(2)
    end
    index = (index % #waypoints) + 1
  else
    bot:wait(1)
  end
end
