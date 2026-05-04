/*
 * Custom frida-trace handler for BCryptHashData.
 *
 * Default frida-trace stub only logs the function name; we need the
 * actual bytes being hashed to reverse-engineer the canonical-string
 * format for think-cell's HMAC scheme.
 *
 * Signature:
 *   NTSTATUS BCryptHashData(
 *     [in, out] BCRYPT_HASH_HANDLE hHash,    // args[0]
 *     [in]      PUCHAR             pbInput,  // args[1]
 *     [in]      ULONG              cbInput,  // args[2]
 *     [in]      ULONG              dwFlags   // args[3]
 *   );
 */
{
  onEnter(log, args, state) {
    const handle = args[0].toString();
    const cbInput = args[2].toInt32();
    const flags = args[3].toInt32();
    let hexInput = '';
    if (cbInput > 0 && cbInput < 65536) {
      try {
        const buf = new Uint8Array(args[1].readByteArray(cbInput));
        let h = '';
        for (let i = 0; i < buf.length; i++) {
          h += buf[i].toString(16).padStart(2, '0');
        }
        hexInput = h;
      } catch (e) {
        hexInput = '<readByteArray failed: ' + e.message + '>';
      }
    } else if (cbInput >= 65536) {
      hexInput = '<too large: ' + cbInput + ' bytes>';
    }
    log('BCryptHashData handle=' + handle +
        ' cbInput=' + cbInput +
        ' flags=' + flags +
        ' input_hex=' + hexInput);
  },
  onLeave(log, retval, state) {
    log('BCryptHashData ret=' + retval.toInt32());
  }
}
