# Chase Motion

Use this skill when the clip contains a chase, pursuit or escape, especially
when the chase includes a physical or weapon exchange.

- Preserve one clear travel direction, terrain and distance relationship.
- The chase is the primary motion: running, vaulting, turning, wall pushes and
  landings must flow into the next action without a neutral reset.
- In a weapon encounter during a chase, contact is transient: strike or parry,
  one sharp contact, immediate deflection or separation, then continue running
  or turning. Do not hold the weapons together, brace in a static lock, stop to
  stare, or wait at the contact point unless the user explicitly requests a
  standoff.
- The approved contract must say `weapon_contact_policy: transient`,
  `post_contact_motion: resume_pursuit` and `allow_weapon_bind: false` for this
  branch.
- The defender must inherit the contact result and keep moving: slide, pivot,
  stumble, redirect or resume pursuit. Do not leave one character frozen while
  the other resumes the chase.
- Show takeoff, leverage point, trajectory and landing for wall steps, vaults,
  slides and rooftop movement. Keep the camera wide enough to preserve feet,
  terrain and weapon paths when they matter.
- For a chase that includes martial arts, combine this rule with the Chinese
  martial-arts skill. Wuxia style changes the footwork and body mechanics, not
  the requirement for continuous pursuit.
