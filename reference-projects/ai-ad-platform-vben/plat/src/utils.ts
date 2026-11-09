export function debounce<F extends (...args: any[]) => any>(
  fn: F,
  delay = 300,
): (...args: Parameters<F>) => void {
  let timer: number | undefined;

  return function debounced(this: ThisParameterType<F>, ...args: Parameters<F>) {
    if (timer !== undefined) {
      window.clearTimeout(timer);
    }

    timer = window.setTimeout(() => {
      fn.apply(this, args);
    }, delay);
  };
}


