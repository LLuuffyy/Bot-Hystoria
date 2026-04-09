-- hello.lua
-- Minimal sanity-check script. Prove the Lua engine is alive by
-- logging a message and reacting to the most common events coming
-- from the MITM proxy.
--
-- Run with:
--     python -m dofus_bot --proxy --script examples/hello.lua

bot:log("hello from Lua! map_id=" .. tostring(bot.character.map_id))

bot:on("map_change", function(data)
  bot:log("map_change -> " .. tostring(data.map_id))
end)

bot:on("fight_start", function()
  bot:log("fight started")
end)

bot:on("fight_end", function()
  bot:log("fight ended")
end)

bot:on("turn_start", function(data)
  bot:log("my turn #" .. tostring(data.turn))
end)
