export function Logo({ name = "Sanad" }: { name?: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span
        aria-hidden="true"
        className="flex h-9 w-9 items-center justify-center rounded-md bg-primary font-display text-lg font-extrabold text-primary-fg"
      >
        S
      </span>
      <span className="font-display text-xl font-extrabold text-primary">{name}</span>
    </span>
  );
}
