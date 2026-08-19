import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function IconBase({ children, ...props }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      {children}
    </svg>
  );
}

export function ArrowRightIcon(props: IconProps) {
  return <IconBase {...props}><path d="M5 12h14M14 7l5 5-5 5" /></IconBase>;
}

export function ShieldIcon(props: IconProps) {
  return <IconBase {...props}><path d="M12 3 5.5 5.6v5.7c0 4.2 2.7 7.4 6.5 9.2 3.8-1.8 6.5-5 6.5-9.2V5.6L12 3Z" /><path d="m9.3 11.8 1.8 1.8 3.8-4" /></IconBase>;
}

export function SparkIcon(props: IconProps) {
  return <IconBase {...props}><path d="m12 2 1.5 5.3L19 9l-5.5 1.7L12 16l-1.5-5.3L5 9l5.5-1.7L12 2Z" /><path d="m19 15 .8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15Z" /></IconBase>;
}

export function MessageIcon(props: IconProps) {
  return <IconBase {...props}><path d="M5 18.2 3.5 21l4-1.2c1.2.5 2.7.8 4.5.8 5 0 9-3.4 9-7.8S17 5 12 5 3 8.4 3 12.8c0 2.1.8 3.9 2 5.4Z" /><path d="M8 12.5h.01M12 12.5h.01M16 12.5h.01" /></IconBase>;
}

export function WalletIcon(props: IconProps) {
  return <IconBase {...props}><path d="M4 6.5h13.5A2.5 2.5 0 0 1 20 9v9H5.5A2.5 2.5 0 0 1 3 15.5V7.8A2.8 2.8 0 0 1 5.8 5H17" /><path d="M15 12h5v3h-5a1.5 1.5 0 1 1 0-3Z" /></IconBase>;
}

export function MenuIcon(props: IconProps) {
  return <IconBase {...props}><path d="M4 7h16M4 12h16M4 17h16" /></IconBase>;
}
