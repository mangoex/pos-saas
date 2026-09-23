export function resolveMenuTheme(palette?: string | null, appearance?: string | null) {
  return {
    palette: ['orange', 'green', 'blue', 'tinto'].includes(palette || '') ? palette! : 'orange',
    appearance: appearance === 'dark' ? 'dark' : 'light',
  };
}
