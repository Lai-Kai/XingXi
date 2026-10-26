/** Deterministic software rendering fixtures; not a reconstruction quality sample. */
export function coloredPlyFixture(count = 8, alpha = true) {
  const header = new TextEncoder().encode(
    `ply\nformat binary_little_endian 1.0\ncomment software fixture\nelement vertex ${count}\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\n${alpha ? "property uchar alpha\n" : ""}end_header\n`,
  );
  const stride = alpha ? 16 : 15;
  const bytes = new Uint8Array(header.length + count * stride);
  bytes.set(header);
  const view = new DataView(bytes.buffer);
  for (let index = 0; index < count; index++) {
    const offset = header.length + index * stride;
    const angle = index * 2.399963229728653;
    const height = (index / Math.max(count - 1, 1)) * 2 - 1;
    const radius = Math.sqrt(1 - height ** 2);
    view.setFloat32(offset, radius * Math.cos(angle), true);
    view.setFloat32(offset + 4, height, true);
    view.setFloat32(offset + 8, radius * Math.sin(angle), true);
    bytes.set([index % 2 ? 0 : 255, 128, index % 2 ? 255 : 0], offset + 12);
    if (alpha) bytes[offset + 15] = index % 2 ? 128 : 255;
  }
  return bytes;
}

export function gaussianPlyFixture(count = 128) {
  const names = [
    "x",
    "y",
    "z",
    "f_dc_0",
    "f_dc_1",
    "f_dc_2",
    "opacity",
    "scale_0",
    "scale_1",
    "scale_2",
    "rot_0",
    "rot_1",
    "rot_2",
    "rot_3",
  ];
  const header = new TextEncoder().encode(
    `ply\nformat binary_little_endian 1.0\ncomment software fixture\nelement vertex ${count}\n${names.map((name) => `property float ${name}\n`).join("")}end_header\n`,
  );
  const bytes = new Uint8Array(header.length + count * names.length * 4);
  bytes.set(header);
  const view = new DataView(bytes.buffer);
  for (let index = 0; index < count; index++) {
    const angle = index * 2.399963229728653;
    const height = (index / Math.max(count - 1, 1)) * 2 - 1;
    const radius = Math.sqrt(1 - height ** 2);
    const values = [
      radius * Math.cos(angle),
      height,
      radius * Math.sin(angle),
      1,
      -0.3,
      -0.3,
      4,
      -2.8,
      -2.8,
      -2.8,
      1,
      0,
      0,
      0,
    ];
    values.forEach((value, column) =>
      view.setFloat32(
        header.length + (index * names.length + column) * 4,
        value,
        true,
      ),
    );
  }
  return bytes;
}
