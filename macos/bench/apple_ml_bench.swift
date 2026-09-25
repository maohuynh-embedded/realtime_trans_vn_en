// Do Apple Translation + SpeechAnalyzer (macOS 26) tren may that.
// Chay: say -v Samantha -o /tmp/probe/en1.aiff "<cau tieng Anh>"; swiftc -O -parse-as-library apple_ml_bench.swift -o /tmp/probe/bench && /tmp/probe/bench
import Speech
import Translation
import AVFoundation
import Foundation

func ms(_ t: Date) -> String { String(format: "%.0f ms", Date().timeIntervalSince(t) * 1000) }

@main
struct Bench {
    static func main() async {
        guard #available(macOS 26.0, *) else { return }

        // ---- Dich: Apple Translation (tren may) ----
        let en = Locale.Language(identifier: "en"), vi = Locale.Language(identifier: "vi")
        let sentences = [
            "Good morning, thanks for joining the call today.",
            "We need to check the UART interrupt handler because the buffer overflows under heavy load, and then we can decide what to do next.",
        ]
        do {
            let s = TranslationSession(installedSource: en, target: vi)
            _ = try await s.translate("warm up")
            for text in sentences {
                var times: [Double] = []
                var out = ""
                for _ in 0..<5 {
                    let t0 = Date()
                    out = try await s.translate(text).targetText
                    times.append(Date().timeIntervalSince(t0) * 1000)
                }
                times.sort()
                print(String(format: "Translation en->vi  median %4.0f ms | %@", times[times.count/2], out))
            }
            let s2 = TranslationSession(installedSource: vi, target: en)
            let vt = "Chúng ta cần kiểm tra lại bộ nhớ đệm vì nó bị tràn khi tải nặng."
            _ = try await s2.translate("xin chào")
            let t0 = Date()
            let r = try await s2.translate(vt).targetText
            print("Translation vi->en  \(ms(t0)) | \(r)")
        } catch { print("translation error:", error) }

        // ---- STT: Apple SpeechAnalyzer (tieng Anh) ----
        do {
            let url = URL(fileURLWithPath: "/tmp/probe/en1.aiff")
            let file = try AVAudioFile(forReading: url)
            let secs = Double(file.length) / file.processingFormat.sampleRate
            let transcriber = SpeechTranscriber(locale: Locale(identifier: "en_US"),
                                                transcriptionOptions: [], reportingOptions: [],
                                                attributeOptions: [])
            let analyzer = SpeechAnalyzer(modules: [transcriber])
            let collector = Task { () -> String in
                var text = ""
                for try await r in transcriber.results { text += String(r.text.characters) }
                return text
            }
            let t0 = Date()
            try await analyzer.start(inputAudioFile: file, finishAfterFile: true)
            let text = try await collector.value
            print(String(format: "SpeechAnalyzer en  %.1fs audio -> %@ | %@", secs, ms(t0), text))
        } catch { print("speech error:", error) }
    }
}
