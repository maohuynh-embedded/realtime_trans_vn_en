// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "sysaudio-capture",
    platforms: [.macOS("14.4")],
    targets: [
        .executableTarget(
            name: "sysaudio-capture",
            path: "Sources/sysaudio-capture",
            exclude: ["Info.plist"]
        ),
    ]
)
