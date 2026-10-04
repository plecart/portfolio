// Pose le mode forcé avant le premier rendu (spec §1.5) — docs/frontend-outillage.md §2.4.
try {
  const theme = localStorage.getItem('theme')
  if (theme === 'light' || theme === 'dark') document.documentElement.dataset.theme = theme
} catch {
  // Stockage refusé (navigation privée, cookies bloqués) : le système décide.
}
