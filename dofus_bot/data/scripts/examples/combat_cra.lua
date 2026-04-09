-- combat_cra.lua
-- Very simple combat rotation for a Cra (archer):
--
--   1. Pick the weakest enemy in range.
--   2. Cast Fleche Magique (spell 161) on it while PA >= 4.
--   3. Pass the turn.
--
-- Spell ids follow the Dofus 1.29 convention (see your client's
-- spells.xml / Hystoria's balance sheet). Adjust as needed.
--
-- Run with:
--     python -m dofus_bot --proxy --script examples/combat_cra.lua

local FLECHE_MAGIQUE = 161  -- 4 PA, long range

local function pick_target()
  local target = nil
  local min_hp = math.huge
  for _, enemy in ipairs(bot.fight.enemies) do
    if enemy.hp > 0 and enemy.hp < min_hp then
      target = enemy
      min_hp = enemy.hp
    end
  end
  return target
end

bot:on("turn_start", function()
  if not bot.fight.my_turn then return end

  local target = pick_target()
  if target == nil then
    bot:log("no valid target, passing")
    bot:end_turn()
    return
  end

  bot:log(
    "targeting enemy " .. tostring(target.id) ..
    " on cell " .. tostring(target.cell) ..
    " (" .. tostring(target.hp) .. " hp)"
  )

  -- Shoot while we have enough PA. We use the convenience
  -- cast_on_enemy helper so the target cell is always up-to-date.
  while bot.character.ap >= 4 do
    local ok = bot:cast_on_enemy(FLECHE_MAGIQUE, target.id)
    if not ok then break end
    bot:wait(0.4)  -- small pause so the server sees a natural rhythm
  end

  bot:end_turn()
end)

bot:on("fight_end", function()
  bot:log("fight over, HP now " .. tostring(bot.character.hp))
end)
