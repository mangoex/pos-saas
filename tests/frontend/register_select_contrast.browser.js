// Run with Playwright CLI run-code after opening the local /admin/register page.
async (page) => {
  const results = [];
  for (const colorScheme of ['dark', 'light']) {
    await page.emulateMedia({ colorScheme, reducedMotion: 'reduce' });
    for (const width of [390, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      await page.reload();
      const selects = page.locator('form select');
      if (await selects.count() !== 2) throw new Error('Expected plan and business type selectors');
      for (const select of await selects.all()) {
        const original = await select.inputValue();
        for (const state of ['rest', 'hover', 'focus']) {
          await select.evaluate(el => el.blur());
          await page.mouse.move(0, 0);
          if (state === 'hover') await select.hover();
          if (state === 'focus') await select.focus();
          // Wait for the existing background transition to finish before measuring.
          await select.evaluate(async el => {
            await Promise.all(el.getAnimations().map(animation => animation.finished));
          });
          const colors = await select.evaluate(el => {
            const style = getComputedStyle(el);
            const luminance = color => {
              const rgb = color.match(/[\d.]+/g).slice(0, 3).map(Number).map(v => {
                v /= 255;
                return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
              });
              return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
            };
            const fg = luminance(style.color);
            const bg = luminance(style.backgroundColor);
            return { ratio: (Math.max(fg, bg) + 0.05) / (Math.min(fg, bg) + 0.05), foreground: style.color, background: style.backgroundColor };
          });
          if (colors.ratio < 4.5) throw new Error(JSON.stringify({ colorScheme, width, state, ...colors }));
          results.push({ colorScheme, width, state, ratio: colors.ratio });
        }
        const choices = await select.locator('option').evaluateAll(options => options.map(option => option.value));
        for (const value of choices) {
          await select.selectOption(value);
          if (await select.inputValue() !== value) throw new Error('Selection not retained');
        }
        await select.selectOption(original);
        const optionsMatch = await select.evaluate(el => {
          const style = getComputedStyle(el);
          return [...el.options].every(option => {
            const optionStyle = getComputedStyle(option);
            return optionStyle.color === style.color && optionStyle.backgroundColor === style.backgroundColor;
          });
        });
        if (!optionsMatch) throw new Error('Native options must use the same contrasting palette');
      }
    }
  }
  return { checks: results.length, minimumContrast: Math.min(...results.map(result => result.ratio)) };
}
