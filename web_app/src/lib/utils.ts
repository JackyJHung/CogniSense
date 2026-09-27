import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

/* tailwind-merge has to be told about the iOS type ramp in index.css. Left to
 * itself it reads `text-footnote` as a text colour, so in `text-footnote
 * text-label-2` it kept only the colour, and the text fell back to body size. */
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [
        {
          text: [
            "large-title",
            "title1",
            "title2",
            "title3",
            "body",
            "callout",
            "subhead",
            "footnote",
            "caption",
            "caption2",
          ],
        },
      ],
    },
  },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
