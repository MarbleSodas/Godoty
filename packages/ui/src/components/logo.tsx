import { ComponentProps } from "solid-js"

export const Mark = (props: { class?: string }) => {
  return (
    <svg
      data-component="logo-mark"
      classList={{ [props.class ?? ""]: !!props.class }}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8 8zm-1-13h2v6h-2zm0 8h2v2h-2z" fill="var(--icon-strong-base)" />
      <circle cx="9" cy="13" r="1.5" fill="var(--icon-strong-base)" />
      <circle cx="15" cy="13" r="1.5" fill="var(--icon-strong-base)" />
    </svg>
  )
}

export const Splash = (props: Pick<ComponentProps<"svg">, "ref" | "class">) => {
  return (
    <svg
      ref={props.ref}
      data-component="logo-splash"
      classList={{ [props.class ?? ""]: !!props.class }}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8 8zm-1-13h2v6h-2zm0 8h2v2h-2z" fill="var(--icon-strong-base)" />
      <circle cx="9" cy="13" r="1.5" fill="var(--icon-strong-base)" />
      <circle cx="15" cy="13" r="1.5" fill="var(--icon-strong-base)" />
    </svg>
  )
}

export const Logo = (props: { class?: string }) => {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 120 24"
      fill="none"
      classList={{ [props.class ?? ""]: !!props.class }}
    >
      <g>
        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8 8zm-1-13h2v6h-2zm0 8h2v2h-2z" fill="var(--icon-strong-base)" />
        <circle cx="9" cy="13" r="1.5" fill="var(--icon-strong-base)" />
        <circle cx="15" cy="13" r="1.5" fill="var(--icon-strong-base)" />
      </g>
      <text x="32" y="18" font-family="sans-serif" font-weight="bold" font-size="18" fill="var(--icon-strong-base)">Godoty</text>
    </svg>
  )
}
