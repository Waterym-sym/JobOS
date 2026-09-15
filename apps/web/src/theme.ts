export const themes = ['desk', 'ops', 'minimal'] as const
export type Theme = (typeof themes)[number]

export function resolveTheme(value: string | null): Theme {
  return themes.includes(value as Theme) ? (value as Theme) : 'desk'
}

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme
  window.localStorage.setItem('jobos.theme', theme)
}
