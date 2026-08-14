// Pipeline de traitement — fichier de démonstration pour nodal (C++).
#include <algorithm>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

namespace util {

std::string normalize(const std::string& text) {
    std::string out = text;
    std::transform(out.begin(), out.end(), out.begin(), ::tolower);
    return out;
}

bool validate(const std::string& path) {
    std::ifstream f(path);
    return f.good();
}

}  // namespace util

struct Stats {
    int count = 0;
    void add(int n) { count += n; }
    int total() const { return count; }
};

class Store {
public:
    explicit Store(const std::string& path) : path_(path) {}
    void save(const std::string& blob);

private:
    std::string path_;
};

// Définition hors-ligne : nodal doit la rattacher à Store.
void Store::save(const std::string& blob) {
    std::ofstream out(path_);
    out << blob;
}

class Pipeline {
public:
    Pipeline(const std::string& in, const std::string& out)
        : input_(in), store_(out) {}

    void run() {
        std::string raw = read();
        std::string clean = util::normalize(raw);
        auto words = tokenize(clean);
        report(words);
        store_.save(clean);
    }

private:
    std::string read() {
        if (!util::validate(input_)) {
            std::cerr << "fichier invalide" << std::endl;
            return "";
        }
        std::ifstream f(input_);
        return std::string((std::istreambuf_iterator<char>(f)), {});
    }

    std::vector<std::string> tokenize(const std::string& text) {
        std::vector<std::string> words;
        std::string cur;
        for (char c : text) {
            if (c == ' ') {
                words.push_back(cur);
                cur.clear();
            } else {
                cur += c;
            }
        }
        return words;
    }

    void report(const std::vector<std::string>& words) {
        stats_.add(static_cast<int>(words.size()));
        std::cout << stats_.total() << std::endl;
    }

    std::string input_;
    Store store_;
    Stats stats_;
};

int main(int argc, char** argv) {
    Pipeline pipe("input.txt", "output.txt");
    pipe.run();
    return 0;
}
