// sysaudio-capture: bat am thanh HE THONG bang Core Audio process tap (macOS 14.4+)
// va ghi PCM float32 xen ke (interleaved) ra stdout. Thong tin dinh dang di ra stderr
// dang mot dong JSON de tien trinh Python doc truoc khi doc PCM.
//
//   sysaudio-capture [--exclude-pid N]... [--seconds S]
//
// --exclude-pid: loai tru am thanh cua tien trinh do (dung cho chinh Python de ban
//                dich phat ra khong bi bat lai -> khong co vong lap).
// --mute-original: tat tieng goc cua cac tien trinh bi bat (chi tap nghe duoc). Tien trinh bi
//                loai tru (--exclude-pid) van phat binh thuong, nen ban dich do chinh app phat
//                ra van nghe duoc. Dung .muted (vo dieu kien, theo CATapDescription.h): che do
//                .mutedWhenTapped chi tat tieng "khi tap dang duoc client KHAC doc" nen tren
//                may that van nghe thay tieng goc. Tieng goc TU KHOI PHUC khi helper thoat
//                (tap rieng tu bi huy cung tien trinh), khong ket im lang.
// --seconds    : tu dung sau S giay (de test); mac dinh chay den khi bi SIGINT/SIGTERM.

import CoreAudio
import AudioToolbox
import Foundation

func fail(_ msg: String) -> Never {
    FileHandle.standardError.write(Data("error: \(msg)\n".utf8))
    exit(1)
}

func check(_ status: OSStatus, _ what: String) {
    if status != noErr { fail("\(what) failed (OSStatus \(status))") }
}

// ---- arguments ----
var excludePIDs: [pid_t] = []
var seconds: Double? = nil
var muteOriginal = false
var args = Array(CommandLine.arguments.dropFirst())
while !args.isEmpty {
    let a = args.removeFirst()
    switch a {
    case "--exclude-pid":
        guard let v = args.first, let p = pid_t(v) else { fail("--exclude-pid needs a number") }
        args.removeFirst(); excludePIDs.append(p)
    case "--mute-original":
        muteOriginal = true
    case "--seconds":
        guard let v = args.first, let s = Double(v) else { fail("--seconds needs a number") }
        args.removeFirst(); seconds = s
    default:
        fail("unknown argument \(a)")
    }
}

// ---- helpers ----
func processObject(for pid: pid_t) -> AudioObjectID? {
    var address = AudioObjectPropertyAddress(
        mSelector: kAudioHardwarePropertyTranslatePIDToProcessObject,
        mScope: kAudioObjectPropertyScopeGlobal,
        mElement: kAudioObjectPropertyElementMain)
    var pidVar = pid
    var obj = AudioObjectID(kAudioObjectUnknown)
    var size = UInt32(MemoryLayout<AudioObjectID>.size)
    let st = AudioObjectGetPropertyData(
        AudioObjectID(kAudioObjectSystemObject), &address,
        UInt32(MemoryLayout<pid_t>.size), &pidVar, &size, &obj)
    return (st == noErr && obj != kAudioObjectUnknown) ? obj : nil
}

func defaultOutputDeviceUID() -> String {
    var address = AudioObjectPropertyAddress(
        mSelector: kAudioHardwarePropertyDefaultSystemOutputDevice,
        mScope: kAudioObjectPropertyScopeGlobal,
        mElement: kAudioObjectPropertyElementMain)
    var dev = AudioDeviceID(kAudioObjectUnknown)
    var size = UInt32(MemoryLayout<AudioDeviceID>.size)
    check(AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &size, &dev),
          "default output device")
    address.mSelector = kAudioDevicePropertyDeviceUID
    var uid: Unmanaged<CFString>?
    size = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
    check(AudioObjectGetPropertyData(dev, &address, 0, nil, &size, &uid), "device UID")
    return (uid?.takeRetainedValue() as String?) ?? ""
}

// ---- tap: mixdown stereo cua TOAN BO he thong, tru cac process bi loai ----
// Process object cua PID bi loai chi ton tai neu tien trinh do da tung dung audio;
// PID khong co process object thi bo qua (khong co gi de loai).
let excludedObjects = excludePIDs.compactMap { processObject(for: $0) }
let tapDesc = CATapDescription(stereoGlobalTapButExcludeProcesses: excludedObjects)
tapDesc.name = "sysaudio-capture tap"
tapDesc.isPrivate = true
tapDesc.muteBehavior = muteOriginal ? .muted : .unmuted

var tapID = AudioObjectID(kAudioObjectUnknown)
check(AudioHardwareCreateProcessTap(tapDesc, &tapID), "AudioHardwareCreateProcessTap")

// dinh dang cua tap
var fmtAddr = AudioObjectPropertyAddress(
    mSelector: kAudioTapPropertyFormat,
    mScope: kAudioObjectPropertyScopeGlobal,
    mElement: kAudioObjectPropertyElementMain)
var asbd = AudioStreamBasicDescription()
var asbdSize = UInt32(MemoryLayout<AudioStreamBasicDescription>.size)
check(AudioObjectGetPropertyData(tapID, &fmtAddr, 0, nil, &asbdSize, &asbd), "tap format")
let channels = Int(asbd.mChannelsPerFrame)
let sampleRate = Int(asbd.mSampleRate)

// ---- aggregate device chua tap ----
let aggUID = UUID().uuidString
let outputUID = defaultOutputDeviceUID()
let aggDesc: [String: Any] = [
    kAudioAggregateDeviceNameKey: "sysaudio-capture aggregate",
    kAudioAggregateDeviceUIDKey: aggUID,
    kAudioAggregateDeviceMainSubDeviceKey: outputUID,
    kAudioAggregateDeviceIsPrivateKey: true,
    kAudioAggregateDeviceIsStackedKey: false,
    kAudioAggregateDeviceTapAutoStartKey: true,
    kAudioAggregateDeviceSubDeviceListKey: [[kAudioSubDeviceUIDKey: outputUID]],
    kAudioAggregateDeviceTapListKey: [[
        kAudioSubTapDriftCompensationKey: true,
        kAudioSubTapUIDKey: tapDesc.uuid.uuidString,
    ]],
]
var aggID = AudioObjectID(kAudioObjectUnknown)
check(AudioHardwareCreateAggregateDevice(aggDesc as CFDictionary, &aggID), "create aggregate device")

// ---- thong tin dinh dang -> stderr (JSON 1 dong) ----
let info = "{\"sample_rate\":\(sampleRate),\"channels\":\(channels),\"format\":\"float32\",\"excluded_pids\":\(excludePIDs),\"excluded_objects\":\(excludedObjects.count)}\n"
FileHandle.standardError.write(Data(info.utf8))

// ---- IO: ghi PCM ra stdout ----
let stdoutFd = FileHandle.standardOutput.fileDescriptor
var ioProc: AudioDeviceIOProcID?
let ioQueue = DispatchQueue(label: "sysaudio.io", qos: .userInteractive)
check(AudioDeviceCreateIOProcIDWithBlock(&ioProc, aggID, ioQueue) { _, inData, _, _, _ in
    let list = UnsafeMutableAudioBufferListPointer(UnsafeMutablePointer(mutating: inData))
    for buf in list {
        guard let p = buf.mData, buf.mDataByteSize > 0 else { continue }
        var remaining = Int(buf.mDataByteSize)
        var ptr = p
        while remaining > 0 {
            let n = write(stdoutFd, ptr, remaining)
            if n <= 0 { exit(0) }   // Python dong pipe -> thoat gon
            remaining -= n
            ptr = ptr.advanced(by: n)
        }
    }
}, "create IOProc")
check(AudioDeviceStart(aggID, ioProc), "start device")

// ---- don dep khi ket thuc ----
func teardown() {
    AudioDeviceStop(aggID, ioProc)
    if let p = ioProc { AudioDeviceDestroyIOProcID(aggID, p) }
    AudioHardwareDestroyAggregateDevice(aggID)
    AudioHardwareDestroyProcessTap(tapID)
}
for sig in [SIGINT, SIGTERM] {
    signal(sig, SIG_IGN)
    let src = DispatchSource.makeSignalSource(signal: sig, queue: .main)
    src.setEventHandler { teardown(); exit(0) }
    src.resume()
}
if let s = seconds {
    DispatchQueue.main.asyncAfter(deadline: .now() + s) { teardown(); exit(0) }
}
dispatchMain()
