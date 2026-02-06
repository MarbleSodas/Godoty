import { ComponentProps, splitProps } from "solid-js"
import { usePlatform } from "@opencode-ai/app/context/platform"

export interface LinkProps extends ComponentProps<"button"> {
  href: string
}

export function Link(props: LinkProps) {
  const platform = usePlatform()
  const [local, rest] = splitProps(props, ["href", "children"])

  return (
    <button class="text-text-strong underline" onClick={() => platform.openLink(local.href)} {...rest}>
      {local.children}
    </button>
  )
}
