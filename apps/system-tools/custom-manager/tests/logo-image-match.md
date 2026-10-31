# HYPRDEBIAN image-reference mask review

The user authorized replacing the previous exact supplied matrix with a 36x36
reconstruction of the screenshot. Only the LARGE mask changes. The native
half-block renderer, smaller masks, gradient, animation and actions are preserved.

The matrix is authored offline from traced contours; it is stored literally in
`src/cli_logo.c`. There is no runtime image loading or geometry generator.

## Reference image vs terminal mask

| Feature | Screenshot observation | Reconstructed mask |
| --- | --- | --- |
| Top | Two narrow, separated tips | Two one-pixel tips on row 1, separated by three empty pixels |
| Proportions | Tall emblem, roughly 3:4 width/height | Occupied bounds x=3..31 and y=1..35, within a 36x36 canvas |
| Left curve | Sloping blade, broad lower bend | Continuous cyan left slope, turning blue/violet toward the base |
| Right curve | Steeper asymmetric edge, red lower flank | Separate upper contour joined to the rounded right/base contour |
| Inner arc | Broad open arc around the small coil | Independent violet/pink arc, open toward the lower right |
| Coil | Compact curled centre, black gaps | Thin inner coil around approximately (21,22), with an empty centre pixel |
| Negative space | Clear separation between blade, arc and centre | Only 64 of the 256 cells in x=12..27, y=13..28 are filled |
| Base | Rounded taper beneath the interior | Joined curved base extending to row 35 |

Two reconstructions were reviewed in monochrome before applying color. The first
was too wide; the second narrows the traced contours and sharpens both tips.
The 36-column, 18-line PTY preview was then inspected both static and animated.
Tests retain dimension, range, checksum and half-block checks and additionally
protect the top opening, occupied width and internal negative space.

At this resolution the fine antialiasing, glow and tiny turns in the reference
cannot be reproduced exactly. Fidelity is an approximation of the emblem, not
pixel equality. The static and animated modes have exactly the same geometry.
