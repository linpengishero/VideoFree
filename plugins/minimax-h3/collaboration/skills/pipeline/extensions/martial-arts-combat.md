id: martial-arts-combat
name: 徒手中国武术
summary: 处理连续重心、徒手、兵器、轻功与追逐中的中国武术动作语法，避免退化为拳击

# 中国武术动作

Use this skill when the approved brief requests Chinese martial arts, kung fu,
wushu, wuxia movement, traditional Chinese combat, or a Chinese martial-arts
weapon. This is a movement skill, not an appearance or story skill.

## Branch selection

Read the approved `martial_arts_plan` before directing:

- `unarmed`: stance transition, whole-body power, entering angle, parry,
  palm/fist/elbow/knee, sweep, throw, lock and grounded recovery.
- `single_weapon`: track the named weapon's grip, striking surface, path,
  contact point, deflection, recovery and ownership.
- `dual_weapon`: track both weapons independently; neither weapon may teleport,
  merge, change type or perform two incompatible contacts.
- `mixed`: keep the weapon hand occupied while the free hand, footwork and body
  angle perform the unarmed action.
- `lightness_chase`: every leap, wall step or landing needs a visible takeoff,
  leverage point, trajectory and landing surface. No weightless flying.

For `context: chase` with a weapon, use `weapon_contact_policy: transient`,
`post_contact_motion: resume_pursuit` and `allow_weapon_bind: false`. A parry
is one sharp contact followed immediately by deflection, separation and the
next running or turning motion.

If style is unspecified, use grounded general Chinese martial arts. Do not
silently turn it into boxing. If a named style is supplied, preserve its broad
visible mechanics without inventing a choreographic form or supernatural move.

## Movement grammar

Write each exchange as:

`起势/步法 -> 身体转移或借力 -> 接触点 -> 受力结果 -> 反应 -> 下一动作`

Use stance changes, waist and hip rotation, whole-body power and whole-body
entry, redirection,
angle changes, short explosive bursts, sweeps, throws and controlled recovery.
The next action inherits the previous balance, distance, facing and occupied
limbs. Keep combat continuous unless the approved motion contract explicitly
allows a pause or standoff.

Do not default to a boxing template: no ring-style bouncing, repeated jab-cross
combos, stationary shoulder-only punching, or generic punch exchange unless the
user explicitly requests boxing or modern kickboxing.

## Weapons

For a sword, sabre, staff, spear, hook, whip or other named weapon, describe
the visible weapon path, contact point, leverage and landing state. Preserve
weapon length and type. A weapon must not change hands without an event; a hand
used to hold or parry cannot simultaneously strike elsewhere. Keep the camera
wide enough to show full weapon length or footwork when necessary.

Do not add named weapons, wirework, qi effects or fantasy powers unless approved
by the user. A weapon cut or thrust must have a visible contact or near-miss and
an inherited recovery state.

## Chases and mixed action

When combined with `chase_motion`, chase momentum drives the first contact and
the result drives the resumed run or pursuit. Do not stop both fighters to
perform isolated poses. A turn, wall step, vault or slide preserves direction
and shows its takeoff and landing.

## Impact and camera

Show power through ground pressure, body displacement, breath, clothing, dust,
weapon vibration and contact feedback, not slow motion by default. Follow the
body line and contact; do not hide contact with random camera shake. Preserve
references as the sole appearance authority.

If dialogue or facial acting is present, let those skills handle speech and
expression while this skill preserves the physical chain.
