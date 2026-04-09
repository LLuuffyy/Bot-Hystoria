-- farm_bouftous.lua
-- Event-driven farming loop for the Astrub bouftou area. The script
-- waits for a `map_change` event, then tries to engage the closest
-- monster on the new map. Once the fight is over it waits a moment
-- and stays idle (you're expected to walk to the next map through
-- the real client, or to extend this script with movement packets
-- once movement injection is implemented).
--
-- Run with:
--     python -m dofus_bot --proxy --script examples/farm_bouftous.lua

local function closest_monster()
  local me = bot.character.cell
  local best = nil
  local best_dist = math.huge
  for _, actor in ipairs(bot.map.monsters) do
    if actor.cell and actor.cell >= 0 then
      local d = math.abs(actor.cell - me)
      if d < best_dist then
        best = actor
        best_dist = d
      end
    end
  end
  return best
end

local function try_engage()
  if bot.fight.is_active then
    return
  end
  local target = closest_monster()
  if target == nil then
    bot:log("no monsters on map " .. tostring(bot.character.map_id))
    return
  end
  bot:log("engaging monster group " .. tostring(target.id) ..
          " on cell " .. tostring(target.cell))
  bot:engage(target.id)
end

bot:on("map_change", function(data)
  bot:log("arrived on map " .. tostring(data.map_id))
  -- Give the server a beat to ship the GM actor list.
  bot:wait(1.0)
  try_engage()
end)

bot:on("actors_update", function()
  -- Retry engaging whenever the actor list changes (new spawn).
  if not bot.fight.is_active then
    try_engage()
  end
end)

bot:on("fight_end", function()
  bot:log("fight done, XP/kamas reflected in client")
end)
