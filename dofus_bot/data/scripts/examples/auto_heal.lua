-- auto_heal.lua
-- Reacts to the "hp_low" event emitted by the combat handler when our
-- own HP drops below 40% of max. Outside of a fight this would be a
-- good place to trigger a bread consumption; inside a fight it logs
-- a warning so you notice it in the console.
--
-- Run with:
--     python -m dofus_bot --proxy --script examples/auto_heal.lua

bot:on("hp_low", function(data)
  local ratio = 0
  if data.max_hp and data.max_hp > 0 then
    ratio = math.floor((data.hp / data.max_hp) * 100)
  end
  if bot.fight.is_active then
    bot:log("!!! LOW HP in fight: " .. tostring(data.hp) ..
            "/" .. tostring(data.max_hp) .. " (" .. ratio .. "%)")
  else
    bot:log("LOW HP out of fight: " .. tostring(data.hp) ..
            "/" .. tostring(data.max_hp))
    -- Example: if you map bread to a dedicated slot you could send
    -- the use-item packet here. The raw format depends on the Dofus
    -- 1.29 server build, so it is left commented-out by default.
    -- bot:send("Oj<slot>")
  end
end)

bot:on("fight_end", function()
  bot:log("fight done, current HP " .. tostring(bot.character.hp) ..
          "/" .. tostring(bot.character.max_hp))
end)
