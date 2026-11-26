// The Azuregos mark: an azure crystal crossed by a ticket on a light blue
// rounded square. Same artwork as the favicon and app icons in public/,
// all rendered by scripts/make_icons.py.
export default function Logo({ size = 28 }: { size?: number }) {
  return (
    <img
      className="logo"
      src="/icons/logo-256.png"
      width={size}
      height={size}
      alt=""
      aria-hidden
      draggable={false}
    />
  );
}
