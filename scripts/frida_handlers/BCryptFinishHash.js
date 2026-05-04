/*
 * Custom frida-trace handler for BCryptFinishHash.
 *
 * Captures the OUTPUT of the hash — the final HMAC bytes that get attached
 * to outbound requests. Cross-correlate with WinHttpAddRequestHeaders to
 * see where the signature lands in the request.
 *
 * Signature:
 *   NTSTATUS BCryptFinishHash(
 *     [in, out] BCRYPT_HASH_HANDLE hHash,    // args[0]
 *     [out]     PUCHAR             pbOutput, // args[1]
 *     [in]      ULONG              cbOutput, // args[2] (16 for MD5/HMAC-MD5; 32 for SHA256/HMAC-SHA256)
 *     [in]      ULONG              dwFlags   // args[3]
 *   );
 */
{
  onEnter(log, args, state) {
    state.hHash = args[0].toString();
    state.outputPtr = args[1];
    state.cbOutput = args[2].toInt32();
  },
  onLeave(log, retval, state) {
    let outputHex = '';
    if (state.cbOutput > 0 && state.cbOutput < 256) {
      try {
        const buf = new Uint8Array(state.outputPtr.readByteArray(state.cbOutput));
        let h = '';
        for (let i = 0; i < buf.length; i++) {
          h += buf[i].toString(16).padStart(2, '0');
        }
        outputHex = h;
      } catch (e) {
        outputHex = '<readByteArray failed: ' + e.message + '>';
      }
    }
    log('BCryptFinishHash hHash=' + state.hHash +
        ' cbOutput=' + state.cbOutput +
        ' (' + (state.cbOutput === 16 ? 'MD5/HMAC-MD5' : state.cbOutput === 32 ? 'SHA256/HMAC-SHA256' : 'other') + ')' +
        ' output_hex=' + outputHex +
        ' ret=' + retval.toInt32());
  }
}
