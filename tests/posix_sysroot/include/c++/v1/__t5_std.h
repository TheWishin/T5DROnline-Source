/* Declaration-only stand-in for the C++ standard library (tests/test_macos_port.py).
 *
 * It lets clang -fsyntax-only check src/ for arm64 macOS on a PC that has no
 * libc++ headers: what matters there is the platform surface (POSIX and the
 * runtime's Win32 shim, LP64 type widths, the macOS libc), not the standard
 * library, which is the same on every host. So the containers are permissive
 * (member templates that accept what the real ones accept, and more); only
 * std::min / std::max keep the real signatures, because a size_t against a
 * uint64_t argument (unsigned long vs unsigned long long on macOS) is exactly
 * the kind of mistake that compiles on Windows and not on a Mac.
 *
 * Nothing here is ever linked or run. Add a declaration when src/ starts using
 * something new (the test names the line). */
#pragma once
#include <stddef.h>
#include <stdint.h>

namespace std {
using size_t = ::size_t;
using ptrdiff_t = ::ptrdiff_t;
using nullptr_t = decltype(nullptr);
using uint8_t = ::uint8_t;   using int8_t = ::int8_t;
using uint16_t = ::uint16_t; using int16_t = ::int16_t;
using uint32_t = ::uint32_t; using int32_t = ::int32_t;
using uint64_t = ::uint64_t; using int64_t = ::int64_t;
using uintptr_t = ::uintptr_t; using intptr_t = ::intptr_t;

/* ---- type traits (the few src/ needs) ---- */
template <class T, T v> struct integral_constant { static constexpr T value = v; using type = integral_constant; constexpr operator T() const { return v; } };
using true_type = integral_constant<bool, true>;
using false_type = integral_constant<bool, false>;
template <class T> struct remove_reference { using type = T; };
template <class T> struct remove_reference<T&> { using type = T; };
template <class T> struct remove_reference<T&&> { using type = T; };
template <class T> using remove_reference_t = typename remove_reference<T>::type;
template <class T> struct remove_cv { using type = T; };
template <class T> struct remove_cv<const T> { using type = T; };
template <class T> struct remove_cv<volatile T> { using type = T; };
template <class T> struct remove_cv<const volatile T> { using type = T; };
template <class T> using remove_cv_t = typename remove_cv<T>::type;
template <class T> using decay_t = remove_cv_t<remove_reference_t<T>>;
template <bool B, class T = void> struct enable_if {};
template <class T> struct enable_if<true, T> { using type = T; };
template <bool B, class T = void> using enable_if_t = typename enable_if<B, T>::type;
template <bool B, class T, class F> struct conditional { using type = T; };
template <class T, class F> struct conditional<false, T, F> { using type = F; };
template <bool B, class T, class F> using conditional_t = typename conditional<B, T, F>::type;
template <class A, class B> struct is_same : false_type {};
template <class A> struct is_same<A, A> : true_type {};
template <class A, class B> inline constexpr bool is_same_v = is_same<A, B>::value;
template <class T> struct is_integral : integral_constant<bool, __is_integral(T)> {};
template <class T> inline constexpr bool is_integral_v = __is_integral(T);
template <class T> struct is_signed : integral_constant<bool, __is_signed(T)> {};
template <class T> struct is_unsigned : integral_constant<bool, __is_unsigned(T)> {};
template <class T> inline constexpr bool is_trivially_copyable_v = __is_trivially_copyable(T);
template <class T> struct is_pointer : false_type {};
template <class T> struct is_pointer<T*> : true_type {};
template <class T> inline constexpr bool is_pointer_v = is_pointer<T>::value;
template <class T> struct make_unsigned { using type = __make_unsigned(T); };
template <class T> using make_unsigned_t = __make_unsigned(T);
template <class T> struct make_signed { using type = __make_signed(T); };
template <class T> using make_signed_t = __make_signed(T);
template <class T> T&& declval() noexcept;
template <class T> struct is_enum : integral_constant<bool, __is_enum(T)> {};
template <class T> inline constexpr bool is_enum_v = __is_enum(T);
template <class T> struct is_floating_point : integral_constant<bool, __is_floating_point(T)> {};
template <class T> inline constexpr bool is_floating_point_v = __is_floating_point(T);
template <class T> struct is_arithmetic : integral_constant<bool, __is_arithmetic(T)> {};
template <class T> inline constexpr bool is_arithmetic_v = __is_arithmetic(T);
template <class T> struct is_class : integral_constant<bool, __is_class(T)> {};
template <class T> struct is_trivially_copyable : integral_constant<bool, __is_trivially_copyable(T)> {};
template <class T> struct is_standard_layout : integral_constant<bool, __is_standard_layout(T)> {};
template <class T> struct underlying_type { using type = __underlying_type(T); };
template <class T> using underlying_type_t = __underlying_type(T);
template <class T> struct is_const : false_type {};
template <class T> struct is_const<const T> : true_type {};
template <class T> struct is_array : false_type {};
template <class T> struct is_array<T[]> : true_type {};
template <class T, size_t N> struct is_array<T[N]> : true_type {};
template <class T> struct remove_pointer { using type = T; };
template <class T> struct remove_pointer<T*> { using type = T; };
template <class T> using remove_pointer_t = typename remove_pointer<T>::type;
template <class T> struct add_pointer { using type = remove_reference_t<T>*; };
template <class T> struct decay { using type = decay_t<T>; };
template <class F, class... A> struct invoke_result { using type = decltype(declval<F>()(declval<A>()...)); };
template <class F, class... A> using invoke_result_t = typename invoke_result<F, A...>::type;
template <class...> using void_t = void;

template <class T> constexpr remove_reference_t<T>&& move(T&& t) noexcept { return static_cast<remove_reference_t<T>&&>(t); }
template <class T> constexpr T&& forward(remove_reference_t<T>& t) noexcept { return static_cast<T&&>(t); }
template <class T> constexpr T&& forward(remove_reference_t<T>&& t) noexcept { return static_cast<T&&>(t); }
template <class T> void swap(T& a, T& b) noexcept;
template <class T, class U = T> T exchange(T& obj, U&& v);

template <class T> class initializer_list {
    const T* b_; size_t n_;
public:
    using value_type = T; using size_type = size_t; using iterator = const T*; using const_iterator = const T*;
    constexpr initializer_list() noexcept : b_(nullptr), n_(0) {}
    constexpr size_t size() const noexcept { return n_; }
    constexpr const T* begin() const noexcept { return b_; }
    constexpr const T* end() const noexcept { return b_ + n_; }
};

template <class T, T... I> struct integer_sequence { using value_type = T; static constexpr size_t size() noexcept { return sizeof...(I); } };
template <size_t... I> using index_sequence = integer_sequence<size_t, I...>;
template <class T, T N> using make_integer_sequence = __make_integer_seq<integer_sequence, T, N>;
template <size_t N> using make_index_sequence = make_integer_sequence<size_t, N>;

/* ---- numeric limits ---- */
template <class T> struct numeric_limits {
    static constexpr bool is_specialized = true;
    static constexpr T min() noexcept { return T(); }
    static constexpr T max() noexcept { return T(); }
    static constexpr T lowest() noexcept { return T(); }
    static constexpr T epsilon() noexcept { return T(); }
    static constexpr T infinity() noexcept { return T(); }
    static constexpr T quiet_NaN() noexcept { return T(); }
};

/* ---- min / max: the real signatures (type width mistakes must not pass) ---- */
template <class T> constexpr const T& min(const T& a, const T& b) { return b < a ? b : a; }
template <class T, class C> constexpr const T& min(const T& a, const T& b, C comp) { return comp(b, a) ? b : a; }
template <class T> constexpr T min(initializer_list<T> l) { return *l.begin(); }
template <class T> constexpr const T& max(const T& a, const T& b) { return a < b ? b : a; }
template <class T, class C> constexpr const T& max(const T& a, const T& b, C comp) { return comp(a, b) ? b : a; }
template <class T> constexpr T max(initializer_list<T> l) { return *l.begin(); }
template <class T> constexpr const T& clamp(const T& v, const T& lo, const T& hi) { return v < lo ? lo : hi < v ? hi : v; }

/* ---- iterators and algorithms: permissive ---- */
struct input_iterator_tag {}; struct forward_iterator_tag : input_iterator_tag {};
struct bidirectional_iterator_tag : forward_iterator_tag {}; struct random_access_iterator_tag : bidirectional_iterator_tag {};
template <class It> struct iterator_traits { using difference_type = ptrdiff_t; using value_type = decay_t<decltype(*declval<It>())>; };
template <class C> auto begin(C& c) -> decltype(c.begin()) { __builtin_unreachable(); }
template <class C> auto end(C& c) -> decltype(c.end()) { __builtin_unreachable(); }
template <class C> auto begin(const C& c) -> decltype(c.begin()) { __builtin_unreachable(); }
template <class C> auto end(const C& c) -> decltype(c.end()) { __builtin_unreachable(); }
template <class T, size_t N> constexpr T* begin(T (&a)[N]) noexcept { return a; }
template <class T, size_t N> constexpr T* end(T (&a)[N]) noexcept { return a + N; }
template <class C> constexpr auto size(const C& c) -> decltype(c.size());
template <class T, size_t N> constexpr size_t size(const T (&)[N]) noexcept { return N; }
template <class C> constexpr auto data(C& c) -> decltype(c.data());
template <class It> It prev(It it, ptrdiff_t n = 1) { __builtin_unreachable(); }
template <class It> It next(It it, ptrdiff_t n = 1) { __builtin_unreachable(); }
template <class It> ptrdiff_t distance(It a, It b) { __builtin_unreachable(); }
template <class It, class D> void advance(It& it, D n) { __builtin_unreachable(); }
template <class C> struct back_insert_iterator { back_insert_iterator& operator*() { __builtin_unreachable(); } back_insert_iterator& operator++() { __builtin_unreachable(); } back_insert_iterator operator++(int) { __builtin_unreachable(); } template <class V> back_insert_iterator& operator=(V&&) { __builtin_unreachable(); } };
template <class C> back_insert_iterator<C> back_inserter(C& c) { __builtin_unreachable(); }

template <class It, class... A> void sort(It a, It b, A... cmp) { __builtin_unreachable(); }
template <class It, class... A> void stable_sort(It a, It b, A... cmp) { __builtin_unreachable(); }
template <class It, class... A> void nth_element(It a, It n, It b, A... cmp) { __builtin_unreachable(); }
template <class It, class... A> void partial_sort(It a, It m, It b, A... cmp) { __builtin_unreachable(); }
template <class It, class T, class... A> It lower_bound(It a, It b, const T& v, A... cmp) { __builtin_unreachable(); }
template <class It, class T, class... A> It upper_bound(It a, It b, const T& v, A... cmp) { __builtin_unreachable(); }
template <class It, class T, class... A> bool binary_search(It a, It b, const T& v, A... cmp) { __builtin_unreachable(); }
template <class It, class... A> It unique(It a, It b, A... pred) { __builtin_unreachable(); }
template <class It, class... A> It max_element(It a, It b, A... cmp) { __builtin_unreachable(); }
template <class It, class... A> It min_element(It a, It b, A... cmp) { __builtin_unreachable(); }
template <class It, class T> It find(It a, It b, const T& v) { __builtin_unreachable(); }
template <class It, class P> It find_if(It a, It b, P p) { __builtin_unreachable(); }
template <class It, class P> It find_if_not(It a, It b, P p) { __builtin_unreachable(); }
template <class It, class T> ptrdiff_t count(It a, It b, const T& v) { __builtin_unreachable(); }
template <class It, class P> ptrdiff_t count_if(It a, It b, P p) { __builtin_unreachable(); }
template <class It, class P> bool any_of(It a, It b, P p) { __builtin_unreachable(); }
template <class It, class P> bool all_of(It a, It b, P p) { __builtin_unreachable(); }
template <class It, class P> bool none_of(It a, It b, P p) { __builtin_unreachable(); }
template <class It, class T> void fill(It a, It b, const T& v) { __builtin_unreachable(); }
template <class It, class N, class T> It fill_n(It a, N n, const T& v) { __builtin_unreachable(); }
template <class It, class O> O copy(It a, It b, O out) { __builtin_unreachable(); }
template <class It, class N, class O> O copy_n(It a, N n, O out) { __builtin_unreachable(); }
template <class It> void reverse(It a, It b) { __builtin_unreachable(); }
template <class It, class P> It remove_if(It a, It b, P p) { __builtin_unreachable(); }
template <class It, class T> It remove(It a, It b, const T& v) { __builtin_unreachable(); }
template <class It, class F> F for_each(It a, It b, F f) { __builtin_unreachable(); }
template <class A, class B, class... C> bool equal(A a1, A a2, B b1, C... rest) { __builtin_unreachable(); }
template <class It, class T> T accumulate(It a, It b, T init) { __builtin_unreachable(); }

/* ---- pair / tuple ---- */
template <class A, class B> struct pair {
    using first_type = A; using second_type = B;
    A first; B second;
    constexpr pair();
    constexpr pair(const A& a, const B& b);
    template <class U, class V> constexpr pair(U&& a, V&& b);
    template <class U, class V> constexpr pair(const pair<U, V>& p);
};
template <class A, class B> bool operator==(const pair<A, B>&, const pair<A, B>&) { __builtin_unreachable(); }
template <class A, class B> bool operator!=(const pair<A, B>&, const pair<A, B>&) { __builtin_unreachable(); }
template <class A, class B> bool operator<(const pair<A, B>&, const pair<A, B>&) { __builtin_unreachable(); }
template <class A, class B> pair<decay_t<A>, decay_t<B>> make_pair(A&& a, B&& b) { __builtin_unreachable(); }
template <class... T> struct tuple {
    constexpr tuple();
    template <class... U> constexpr tuple(U&&... u);
};
template <class... T> bool operator<(const tuple<T...>&, const tuple<T...>&) { __builtin_unreachable(); }
template <class... T> bool operator==(const tuple<T...>&, const tuple<T...>&) { __builtin_unreachable(); }
template <class... T> tuple<decay_t<T>...> make_tuple(T&&... t) { __builtin_unreachable(); }
template <class... T> tuple<T&...> tie(T&... t) { __builtin_unreachable(); }
template <size_t I, class T> struct __t5_pick;
template <class H, class... R> struct __t5_pick<0, tuple<H, R...>> { using type = H; };
template <size_t I, class H, class... R> struct __t5_pick<I, tuple<H, R...>> { using type = typename __t5_pick<I - 1, tuple<R...>>::type; };
template <size_t I, class... T> typename __t5_pick<I, tuple<T...>>::type& get(tuple<T...>& t) { __builtin_unreachable(); }
template <size_t I, class... T> const typename __t5_pick<I, tuple<T...>>::type& get(const tuple<T...>& t) { __builtin_unreachable(); }
template <size_t I, class A, class B> conditional_t<I == 0, A, B>& get(pair<A, B>& p) { __builtin_unreachable(); }
template <size_t I, class A, class B> const conditional_t<I == 0, A, B>& get(const pair<A, B>& p) { __builtin_unreachable(); }

/* ---- string ---- */
template <class C> struct char_traits {};
template <class C> class allocator {};
class string {
public:
    using value_type = char; using size_type = size_t; using difference_type = ptrdiff_t;
    using iterator = char*; using const_iterator = const char*; using reference = char&; using const_reference = const char&;
    static constexpr size_t npos = (size_t)-1;
    string() { __builtin_unreachable(); }
    string(const string&) { __builtin_unreachable(); }
    string(string&&) noexcept { __builtin_unreachable(); }
    string(const char* s) { __builtin_unreachable(); }
    string(const char* s, size_t n) { __builtin_unreachable(); }
    string(size_t n, char c) { __builtin_unreachable(); }
    string(const string& s, size_t pos, size_t n = npos) { __builtin_unreachable(); }
    template <class It> string(It a, It b) { __builtin_unreachable(); }
    string(initializer_list<char>) { __builtin_unreachable(); }
    string& operator=(const string&) { __builtin_unreachable(); }
    string& operator=(string&&) noexcept { __builtin_unreachable(); }
    string& operator=(const char*) { __builtin_unreachable(); }
    string& operator=(char) { __builtin_unreachable(); }
    const char* c_str() const noexcept { __builtin_unreachable(); }
    const char* data() const noexcept { __builtin_unreachable(); }
    char* data() noexcept { __builtin_unreachable(); }
    size_t size() const noexcept { __builtin_unreachable(); }
    size_t length() const noexcept { __builtin_unreachable(); }
    size_t capacity() const noexcept { __builtin_unreachable(); }
    bool empty() const noexcept { __builtin_unreachable(); }
    void clear() noexcept { __builtin_unreachable(); }
    void reserve(size_t) { __builtin_unreachable(); }
    void resize(size_t, char = 0) { __builtin_unreachable(); }
    void push_back(char) { __builtin_unreachable(); }
    void pop_back() { __builtin_unreachable(); }
    char& back() { __builtin_unreachable(); } const char& back() const { __builtin_unreachable(); }
    char& front() { __builtin_unreachable(); } const char& front() const { __builtin_unreachable(); }
    char& operator[](size_t) { __builtin_unreachable(); } const char& operator[](size_t) const { __builtin_unreachable(); }
    char& at(size_t) { __builtin_unreachable(); } const char& at(size_t) const { __builtin_unreachable(); }
    char* begin() { __builtin_unreachable(); } char* end() { __builtin_unreachable(); } const char* begin() const { __builtin_unreachable(); } const char* end() const { __builtin_unreachable(); }
    const char* cbegin() const { __builtin_unreachable(); } const char* cend() const { __builtin_unreachable(); }
    template <class... A> string& append(A&&...) { __builtin_unreachable(); }
    template <class... A> string& assign(A&&...) { __builtin_unreachable(); }
    template <class... A> string& insert(A&&...) { __builtin_unreachable(); }
    template <class... A> string& replace(A&&...) { __builtin_unreachable(); }
    string& erase(size_t pos = 0, size_t n = npos) { __builtin_unreachable(); }
    char* erase(const char* it) { __builtin_unreachable(); }
    char* erase(const char* a, const char* b) { __builtin_unreachable(); }
    string& operator+=(const string&) { __builtin_unreachable(); }
    string& operator+=(const char*) { __builtin_unreachable(); }
    string& operator+=(char) { __builtin_unreachable(); }
    string substr(size_t pos = 0, size_t n = npos) const { __builtin_unreachable(); }
    template <class S> size_t find(const S& s, size_t pos = 0) const { __builtin_unreachable(); }
    size_t find(const char* s, size_t pos, size_t n) const { __builtin_unreachable(); }
    template <class S> size_t rfind(const S& s, size_t pos = npos) const { __builtin_unreachable(); }
    template <class S> size_t find_first_of(const S& s, size_t pos = 0) const { __builtin_unreachable(); }
    template <class S> size_t find_last_of(const S& s, size_t pos = npos) const { __builtin_unreachable(); }
    template <class S> size_t find_first_not_of(const S& s, size_t pos = 0) const { __builtin_unreachable(); }
    template <class S> size_t find_last_not_of(const S& s, size_t pos = npos) const { __builtin_unreachable(); }
    template <class... A> int compare(A&&...) const { __builtin_unreachable(); }
    template <class S> bool starts_with(const S&) const { __builtin_unreachable(); }
    template <class S> bool ends_with(const S&) const { __builtin_unreachable(); }
    void swap(string&) { __builtin_unreachable(); }
};
string operator+(const string&, const string&) { __builtin_unreachable(); }
string operator+(const string&, const char*) { __builtin_unreachable(); }
string operator+(const char*, const string&) { __builtin_unreachable(); }
string operator+(const string&, char) { __builtin_unreachable(); }
string operator+(char, const string&) { __builtin_unreachable(); }
string operator+(string&&, const string&) { __builtin_unreachable(); }
string operator+(string&&, const char*) { __builtin_unreachable(); }
string operator+(string&&, char) { __builtin_unreachable(); }
bool operator==(const string&, const string&) { __builtin_unreachable(); }
bool operator==(const string&, const char*) { __builtin_unreachable(); }
bool operator==(const char*, const string&) { __builtin_unreachable(); }
bool operator!=(const string&, const string&) { __builtin_unreachable(); }
bool operator!=(const string&, const char*) { __builtin_unreachable(); }
bool operator!=(const char*, const string&) { __builtin_unreachable(); }
bool operator<(const string&, const string&) { __builtin_unreachable(); }
bool operator>(const string&, const string&) { __builtin_unreachable(); }
bool operator<=(const string&, const string&) { __builtin_unreachable(); }
bool operator>=(const string&, const string&) { __builtin_unreachable(); }
string to_string(int) { __builtin_unreachable(); } string to_string(unsigned) { __builtin_unreachable(); } string to_string(long) { __builtin_unreachable(); } string to_string(unsigned long) { __builtin_unreachable(); }
string to_string(long long) { __builtin_unreachable(); } string to_string(unsigned long long) { __builtin_unreachable(); } string to_string(double) { __builtin_unreachable(); } string to_string(float) { __builtin_unreachable(); }
int stoi(const string&, size_t* = nullptr, int = 10) { __builtin_unreachable(); }
long stol(const string&, size_t* = nullptr, int = 10) { __builtin_unreachable(); }
unsigned long stoul(const string&, size_t* = nullptr, int = 10) { __builtin_unreachable(); }
unsigned long long stoull(const string&, size_t* = nullptr, int = 10) { __builtin_unreachable(); }
long long stoll(const string&, size_t* = nullptr, int = 10) { __builtin_unreachable(); }
double stod(const string&, size_t* = nullptr) { __builtin_unreachable(); }
float stof(const string&, size_t* = nullptr) { __builtin_unreachable(); }
class string_view {
public:
    static constexpr size_t npos = (size_t)-1;
    string_view() noexcept;
    string_view(const char*);
    string_view(const char*, size_t);
    string_view(const string&);
    const char* data() const noexcept; size_t size() const noexcept; bool empty() const noexcept;
    const char* begin() const; const char* end() const;
    char operator[](size_t) const;
    string_view substr(size_t pos = 0, size_t n = npos) const;
    template <class S> size_t find(const S& s, size_t pos = 0) const { __builtin_unreachable(); }
};
template <class T> struct hash { size_t operator()(const T&) const { __builtin_unreachable(); } };

/* ---- containers ---- */
template <class T, class A = allocator<T>> class vector {
public:
    using value_type = T; using size_type = size_t; using difference_type = ptrdiff_t;
    using reference = T&; using const_reference = const T&;
    using iterator = T*; using const_iterator = const T*; using reverse_iterator = T*; using const_reverse_iterator = const T*;
    vector() { __builtin_unreachable(); }
    explicit vector(size_t n) { __builtin_unreachable(); }
    vector(size_t n, const T& v) { __builtin_unreachable(); }
    template <class It> vector(It a, It b) { __builtin_unreachable(); }
    vector(initializer_list<T>) { __builtin_unreachable(); }
    vector(const vector&) { __builtin_unreachable(); }
    vector(vector&&) noexcept { __builtin_unreachable(); }
    vector& operator=(const vector&) { __builtin_unreachable(); }
    vector& operator=(vector&&) noexcept { __builtin_unreachable(); }
    vector& operator=(initializer_list<T>) { __builtin_unreachable(); }
    T* data() noexcept { __builtin_unreachable(); } const T* data() const noexcept { __builtin_unreachable(); }
    size_t size() const noexcept { __builtin_unreachable(); } size_t capacity() const noexcept { __builtin_unreachable(); } bool empty() const noexcept { __builtin_unreachable(); }
    void clear() noexcept { __builtin_unreachable(); } void reserve(size_t) { __builtin_unreachable(); } void resize(size_t) { __builtin_unreachable(); } void resize(size_t, const T&) { __builtin_unreachable(); } void shrink_to_fit() { __builtin_unreachable(); }
    void push_back(const T&) { __builtin_unreachable(); } void push_back(T&&) { __builtin_unreachable(); } void pop_back() { __builtin_unreachable(); }
    template <class... V> T& emplace_back(V&&...) { __builtin_unreachable(); }
    T& operator[](size_t) { __builtin_unreachable(); } const T& operator[](size_t) const { __builtin_unreachable(); }
    T& at(size_t) { __builtin_unreachable(); } const T& at(size_t) const { __builtin_unreachable(); }
    T& back() { __builtin_unreachable(); } const T& back() const { __builtin_unreachable(); } T& front() { __builtin_unreachable(); } const T& front() const { __builtin_unreachable(); }
    T* begin() { __builtin_unreachable(); } T* end() { __builtin_unreachable(); } const T* begin() const { __builtin_unreachable(); } const T* end() const { __builtin_unreachable(); }
    const T* cbegin() const { __builtin_unreachable(); } const T* cend() const { __builtin_unreachable(); }
    T* rbegin() { __builtin_unreachable(); } T* rend() { __builtin_unreachable(); } const T* rbegin() const { __builtin_unreachable(); } const T* rend() const { __builtin_unreachable(); }
    template <class... V> T* insert(const T* pos, V&&...) { __builtin_unreachable(); }
    T* insert(const T* pos, const T& v) { __builtin_unreachable(); }
    T* insert(const T* pos, initializer_list<T> l) { __builtin_unreachable(); }
    template <class... V> T* emplace(const T* pos, V&&...) { __builtin_unreachable(); }
    T* erase(const T* pos) { __builtin_unreachable(); } T* erase(const T* a, const T* b) { __builtin_unreachable(); }
    template <class... V> void assign(V&&...) { __builtin_unreachable(); }
    void swap(vector&) { __builtin_unreachable(); }
};
template <class T, class A> bool operator==(const vector<T, A>&, const vector<T, A>&) { __builtin_unreachable(); }
template <class T, class A> bool operator!=(const vector<T, A>&, const vector<T, A>&) { __builtin_unreachable(); }
template <class T, size_t N> struct array {
    T __elems[N > 0 ? N : 1];
    using value_type = T; using size_type = size_t; using iterator = T*; using const_iterator = const T*;
    constexpr T& operator[](size_t i) { return __elems[i]; }
    constexpr const T& operator[](size_t i) const { return __elems[i]; }
    constexpr T* data() noexcept { return __elems; } constexpr const T* data() const noexcept { return __elems; }
    constexpr size_t size() const noexcept { return N; } constexpr bool empty() const noexcept { return N == 0; }
    constexpr T* begin() noexcept { return __elems; } constexpr T* end() noexcept { return __elems + N; }
    constexpr const T* begin() const noexcept { return __elems; } constexpr const T* end() const noexcept { return __elems + N; }
    constexpr T& front() { return __elems[0]; } constexpr T& back() { return __elems[N - 1]; }
    constexpr void fill(const T& v);
};
template <class K, class V> struct __t5_node_it {
    pair<const K, V>& operator*() const { __builtin_unreachable(); } pair<const K, V>* operator->() const { __builtin_unreachable(); }
    __t5_node_it& operator++() { __builtin_unreachable(); } __t5_node_it operator++(int) { __builtin_unreachable(); } __t5_node_it& operator--() { __builtin_unreachable(); } __t5_node_it operator--(int) { __builtin_unreachable(); }
    bool operator==(const __t5_node_it&) const { __builtin_unreachable(); } bool operator!=(const __t5_node_it&) const { __builtin_unreachable(); }
};
template <class K> struct __t5_key_it {
    const K& operator*() const { __builtin_unreachable(); } const K* operator->() const { __builtin_unreachable(); }
    __t5_key_it& operator++() { __builtin_unreachable(); } __t5_key_it operator++(int) { __builtin_unreachable(); } __t5_key_it& operator--() { __builtin_unreachable(); } __t5_key_it operator--(int) { __builtin_unreachable(); }
    bool operator==(const __t5_key_it&) const { __builtin_unreachable(); } bool operator!=(const __t5_key_it&) const { __builtin_unreachable(); }
};
template <class T> struct less { constexpr bool operator()(const T& a, const T& b) const; };
template <class T> struct greater { constexpr bool operator()(const T& a, const T& b) const; };
template <class T> struct equal_to { constexpr bool operator()(const T& a, const T& b) const; };
template <class K, class V, class Cmp = less<K>, class A = allocator<pair<const K, V>>> class map {
public:
    using key_type = K; using mapped_type = V; using value_type = pair<const K, V>; using size_type = size_t;
    using iterator = __t5_node_it<K, V>; using const_iterator = __t5_node_it<K, V>;
    using reverse_iterator = __t5_node_it<K, V>; using const_reverse_iterator = __t5_node_it<K, V>;
    map() { __builtin_unreachable(); } map(initializer_list<value_type>) { __builtin_unreachable(); } map(const map&) { __builtin_unreachable(); } map(map&&) noexcept { __builtin_unreachable(); }
    map& operator=(const map&) { __builtin_unreachable(); } map& operator=(map&&) noexcept { __builtin_unreachable(); }
    V& operator[](const K&) { __builtin_unreachable(); } V& operator[](K&&) { __builtin_unreachable(); }
    V& at(const K&) { __builtin_unreachable(); } const V& at(const K&) const { __builtin_unreachable(); }
    iterator begin() const { __builtin_unreachable(); } iterator end() const { __builtin_unreachable(); } iterator rbegin() const { __builtin_unreachable(); } iterator rend() const { __builtin_unreachable(); }
    iterator find(const K&) const { __builtin_unreachable(); } size_t count(const K&) const { __builtin_unreachable(); } bool contains(const K&) const { __builtin_unreachable(); }
    iterator lower_bound(const K&) const { __builtin_unreachable(); } iterator upper_bound(const K&) const { __builtin_unreachable(); }
    size_t size() const noexcept { __builtin_unreachable(); } bool empty() const noexcept { __builtin_unreachable(); } void clear() noexcept { __builtin_unreachable(); }
    template <class... A2> pair<iterator, bool> emplace(A2&&...) { __builtin_unreachable(); }
    template <class... A2> pair<iterator, bool> try_emplace(A2&&...) { __builtin_unreachable(); }
    template <class... A2> pair<iterator, bool> insert(A2&&...) { __builtin_unreachable(); }
    pair<iterator, bool> insert(const value_type&) { __builtin_unreachable(); }
    template <class... A2> pair<iterator, bool> insert_or_assign(A2&&...) { __builtin_unreachable(); }
    size_t erase(const K&) { __builtin_unreachable(); } iterator erase(iterator) { __builtin_unreachable(); } iterator erase(iterator, iterator) { __builtin_unreachable(); }
};
template <class K, class V, class H = hash<K>, class E = equal_to<K>, class A = allocator<pair<const K, V>>>
class unordered_map : public map<K, V> { public: void reserve(size_t) { __builtin_unreachable(); } };
template <class K, class Cmp = less<K>, class A = allocator<K>> class set {
public:
    using key_type = K; using value_type = K; using size_type = size_t;
    using iterator = __t5_key_it<K>; using const_iterator = __t5_key_it<K>;
    set() { __builtin_unreachable(); } set(initializer_list<K>) { __builtin_unreachable(); } template <class It> set(It, It) { __builtin_unreachable(); } set(const set&) { __builtin_unreachable(); } set(set&&) noexcept { __builtin_unreachable(); }
    set& operator=(const set&) { __builtin_unreachable(); } set& operator=(set&&) noexcept { __builtin_unreachable(); }
    iterator begin() const { __builtin_unreachable(); } iterator end() const { __builtin_unreachable(); }
    iterator find(const K&) const { __builtin_unreachable(); } size_t count(const K&) const { __builtin_unreachable(); } bool contains(const K&) const { __builtin_unreachable(); }
    iterator lower_bound(const K&) const { __builtin_unreachable(); } iterator upper_bound(const K&) const { __builtin_unreachable(); }
    size_t size() const noexcept { __builtin_unreachable(); } bool empty() const noexcept { __builtin_unreachable(); } void clear() noexcept { __builtin_unreachable(); }
    template <class... A2> pair<iterator, bool> insert(A2&&...) { __builtin_unreachable(); }
    pair<iterator, bool> insert(const K&) { __builtin_unreachable(); }
    template <class... A2> pair<iterator, bool> emplace(A2&&...) { __builtin_unreachable(); }
    size_t erase(const K&) { __builtin_unreachable(); } iterator erase(iterator) { __builtin_unreachable(); }
};
template <class K, class H = hash<K>, class E = equal_to<K>, class A = allocator<K>> class unordered_set : public set<K> {};
template <class T, class A = allocator<T>> class deque : public vector<T> {
public:
    using vector<T>::vector;
    void push_front(const T&) { __builtin_unreachable(); } void pop_front() { __builtin_unreachable(); }
    template <class... V> T& emplace_front(V&&...) { __builtin_unreachable(); }
};

/* ---- smart pointers, function ---- */
template <class T> struct default_delete { void operator()(T*) const { __builtin_unreachable(); } };
template <class T, class D = default_delete<T>> class unique_ptr {
public:
    constexpr unique_ptr() noexcept; constexpr unique_ptr(nullptr_t) noexcept; explicit unique_ptr(T*) noexcept;
    unique_ptr(T*, D) noexcept { __builtin_unreachable(); } unique_ptr(unique_ptr&&) noexcept { __builtin_unreachable(); } template <class U, class E> unique_ptr(unique_ptr<U, E>&&) noexcept { __builtin_unreachable(); }
    unique_ptr& operator=(unique_ptr&&) noexcept { __builtin_unreachable(); } unique_ptr& operator=(nullptr_t) noexcept { __builtin_unreachable(); }
    T* get() const noexcept { __builtin_unreachable(); } T* release() noexcept { __builtin_unreachable(); } void reset(T* = nullptr) noexcept { __builtin_unreachable(); }
    T& operator*() const { __builtin_unreachable(); } T* operator->() const noexcept { __builtin_unreachable(); } explicit operator bool() const noexcept { __builtin_unreachable(); }
};
template <class T, class D> class unique_ptr<T[], D> {
public:
    constexpr unique_ptr() noexcept; explicit unique_ptr(T*) noexcept; unique_ptr(unique_ptr&&) noexcept;
    unique_ptr& operator=(unique_ptr&&) noexcept { __builtin_unreachable(); }
    T* get() const noexcept { __builtin_unreachable(); } void reset(T* = nullptr) noexcept { __builtin_unreachable(); } T& operator[](size_t) const { __builtin_unreachable(); } explicit operator bool() const noexcept { __builtin_unreachable(); }
};
template <class T, class... A> unique_ptr<T> make_unique(A&&...) { __builtin_unreachable(); }
template <class T> class shared_ptr {
public:
    constexpr shared_ptr() noexcept; constexpr shared_ptr(nullptr_t) noexcept; template <class U> explicit shared_ptr(U*);
    shared_ptr(const shared_ptr&) noexcept { __builtin_unreachable(); } shared_ptr(shared_ptr&&) noexcept { __builtin_unreachable(); } template <class U> shared_ptr(const shared_ptr<U>&) noexcept { __builtin_unreachable(); }
    shared_ptr& operator=(const shared_ptr&) noexcept { __builtin_unreachable(); } shared_ptr& operator=(shared_ptr&&) noexcept { __builtin_unreachable(); }
    T* get() const noexcept { __builtin_unreachable(); } void reset() noexcept { __builtin_unreachable(); } template <class U> void reset(U*) { __builtin_unreachable(); }
    T& operator*() const noexcept { __builtin_unreachable(); } T* operator->() const noexcept { __builtin_unreachable(); } explicit operator bool() const noexcept { __builtin_unreachable(); } long use_count() const noexcept { __builtin_unreachable(); }
    void swap(shared_ptr&) noexcept { __builtin_unreachable(); }
};
template <class T, class... A> shared_ptr<T> make_shared(A&&...) { __builtin_unreachable(); }
template <class> class function;
template <class R, class... A> class function<R(A...)> {
public:
    function() noexcept { __builtin_unreachable(); } function(nullptr_t) noexcept { __builtin_unreachable(); } function(const function&) { __builtin_unreachable(); } function(function&&) noexcept { __builtin_unreachable(); }
    template <class F> function(F) { __builtin_unreachable(); }
    function& operator=(const function&) { __builtin_unreachable(); } function& operator=(function&&) noexcept { __builtin_unreachable(); } function& operator=(nullptr_t) noexcept { __builtin_unreachable(); }
    template <class F> function& operator=(F&&) { __builtin_unreachable(); }
    R operator()(A...) const { __builtin_unreachable(); } explicit operator bool() const noexcept { __builtin_unreachable(); }
};

/* ---- atomics ---- */
enum memory_order { memory_order_relaxed, memory_order_consume, memory_order_acquire, memory_order_release,
                    memory_order_acq_rel, memory_order_seq_cst };
template <class T> struct atomic {
    using value_type = T;
    atomic() noexcept = default;
    constexpr atomic(T v) noexcept : __v(v) {}
    atomic(const atomic&) = delete;
    atomic& operator=(const atomic&) = delete;
    T operator=(T v) noexcept { __builtin_unreachable(); }
    T operator=(T v) volatile noexcept { __builtin_unreachable(); }
    operator T() const noexcept { __builtin_unreachable(); }
    operator T() const volatile noexcept { __builtin_unreachable(); }
    T load(memory_order = memory_order_seq_cst) const noexcept { __builtin_unreachable(); }
    T load(memory_order = memory_order_seq_cst) const volatile noexcept { __builtin_unreachable(); }
    void store(T, memory_order = memory_order_seq_cst) noexcept { __builtin_unreachable(); }
    void store(T, memory_order = memory_order_seq_cst) volatile noexcept { __builtin_unreachable(); }
    T exchange(T, memory_order = memory_order_seq_cst) noexcept { __builtin_unreachable(); }
    bool compare_exchange_weak(T&, T, memory_order = memory_order_seq_cst) noexcept { __builtin_unreachable(); }
    bool compare_exchange_weak(T&, T, memory_order, memory_order) noexcept { __builtin_unreachable(); }
    bool compare_exchange_strong(T&, T, memory_order = memory_order_seq_cst) noexcept { __builtin_unreachable(); }
    bool compare_exchange_strong(T&, T, memory_order, memory_order) noexcept { __builtin_unreachable(); }
    template <class D> T fetch_add(D, memory_order = memory_order_seq_cst) noexcept { __builtin_unreachable(); }
    template <class D> T fetch_sub(D, memory_order = memory_order_seq_cst) noexcept { __builtin_unreachable(); }
    T fetch_and(T, memory_order = memory_order_seq_cst) noexcept { __builtin_unreachable(); }
    T fetch_or(T, memory_order = memory_order_seq_cst) noexcept { __builtin_unreachable(); }
    T fetch_xor(T, memory_order = memory_order_seq_cst) noexcept { __builtin_unreachable(); }
    T operator++() noexcept { __builtin_unreachable(); } T operator++(int) noexcept { __builtin_unreachable(); } T operator--() noexcept { __builtin_unreachable(); } T operator--(int) noexcept { __builtin_unreachable(); }
    template <class D> T operator+=(D) noexcept { __builtin_unreachable(); } template <class D> T operator-=(D) noexcept { __builtin_unreachable(); }
    T operator|=(T) noexcept { __builtin_unreachable(); } T operator&=(T) noexcept { __builtin_unreachable(); } T operator^=(T) noexcept { __builtin_unreachable(); }
    bool is_lock_free() const noexcept { __builtin_unreachable(); }
    T __v;
};
struct atomic_flag {
    bool test_and_set(memory_order = memory_order_seq_cst) noexcept { __builtin_unreachable(); }
    void clear(memory_order = memory_order_seq_cst) noexcept { __builtin_unreachable(); }
    bool test(memory_order = memory_order_seq_cst) const noexcept { __builtin_unreachable(); }
};
void atomic_thread_fence(memory_order) noexcept { __builtin_unreachable(); }
void atomic_signal_fence(memory_order) noexcept { __builtin_unreachable(); }
using atomic_bool = atomic<bool>; using atomic_int = atomic<int>; using atomic_uint = atomic<unsigned>;
using atomic_uint32_t = atomic<uint32_t>; using atomic_uint64_t = atomic<uint64_t>;

/* ---- threads and locks ---- */
class mutex { public: constexpr mutex() noexcept; mutex(const mutex&) = delete; void lock(); bool try_lock(); void unlock(); };
class recursive_mutex { public: recursive_mutex() { __builtin_unreachable(); } void lock() { __builtin_unreachable(); } bool try_lock() { __builtin_unreachable(); } void unlock() { __builtin_unreachable(); } };
class shared_mutex { public: shared_mutex() { __builtin_unreachable(); } void lock() { __builtin_unreachable(); } void unlock() { __builtin_unreachable(); } void lock_shared() { __builtin_unreachable(); } void unlock_shared() { __builtin_unreachable(); } };
struct defer_lock_t {}; struct try_to_lock_t {}; struct adopt_lock_t {};
inline constexpr defer_lock_t defer_lock{}; inline constexpr try_to_lock_t try_to_lock{}; inline constexpr adopt_lock_t adopt_lock{};
template <class M> class lock_guard { public: explicit lock_guard(M&) { __builtin_unreachable(); } lock_guard(M&, adopt_lock_t) { __builtin_unreachable(); } ~lock_guard() { __builtin_unreachable(); } lock_guard(const lock_guard&) = delete; };
template <class M> class unique_lock {
public:
    unique_lock() noexcept { __builtin_unreachable(); } explicit unique_lock(M&) { __builtin_unreachable(); } unique_lock(M&, defer_lock_t) noexcept { __builtin_unreachable(); } unique_lock(M&, try_to_lock_t) { __builtin_unreachable(); }
    unique_lock(M&, adopt_lock_t) { __builtin_unreachable(); } ~unique_lock() { __builtin_unreachable(); } unique_lock(unique_lock&&) noexcept { __builtin_unreachable(); } unique_lock& operator=(unique_lock&&) noexcept { __builtin_unreachable(); }
    void lock() { __builtin_unreachable(); } bool try_lock() { __builtin_unreachable(); } void unlock() { __builtin_unreachable(); } bool owns_lock() const noexcept { __builtin_unreachable(); } explicit operator bool() const noexcept { __builtin_unreachable(); } M* mutex() const noexcept { __builtin_unreachable(); }
};
template <class M> class shared_lock { public: explicit shared_lock(M&) { __builtin_unreachable(); } ~shared_lock() { __builtin_unreachable(); } };
template <class... M> class scoped_lock { public: explicit scoped_lock(M&...) { __builtin_unreachable(); } ~scoped_lock() { __builtin_unreachable(); } };
struct once_flag { constexpr once_flag() noexcept; once_flag(const once_flag&) = delete; };
template <class F, class... A> void call_once(once_flag&, F&&, A&&...) { __builtin_unreachable(); }
namespace chrono {
template <class R, class P = void> class duration { public: constexpr duration() { __builtin_unreachable(); } template <class R2> constexpr duration(const R2&) { __builtin_unreachable(); } constexpr R count() const { __builtin_unreachable(); } };
using nanoseconds = duration<long long>; using microseconds = duration<long long>; using milliseconds = duration<long long>;
using seconds = duration<long long>;
template <class C, class D = nanoseconds> class time_point { public: D time_since_epoch() const { __builtin_unreachable(); } };
struct steady_clock { using duration = nanoseconds; using time_point = chrono::time_point<steady_clock>; static time_point now() noexcept { __builtin_unreachable(); } };
template <class To, class D> constexpr To duration_cast(const D&) { __builtin_unreachable(); }
}
class condition_variable {
public:
    condition_variable() { __builtin_unreachable(); } void notify_one() noexcept { __builtin_unreachable(); } void notify_all() noexcept { __builtin_unreachable(); }
    void wait(unique_lock<mutex>&) { __builtin_unreachable(); } template <class P> void wait(unique_lock<mutex>&, P) { __builtin_unreachable(); }
    template <class D> int wait_for(unique_lock<mutex>&, const D&) { __builtin_unreachable(); } template <class D, class P> bool wait_for(unique_lock<mutex>&, const D&, P) { __builtin_unreachable(); }
};
class thread {
public:
    class id { public: bool operator==(const id&) const { __builtin_unreachable(); } bool operator!=(const id&) const { __builtin_unreachable(); } };
    thread() noexcept { __builtin_unreachable(); } template <class F, class... A> explicit thread(F&&, A&&...) { __builtin_unreachable(); } thread(thread&&) noexcept { __builtin_unreachable(); } ~thread() { __builtin_unreachable(); }
    thread& operator=(thread&&) noexcept { __builtin_unreachable(); } void join() { __builtin_unreachable(); } void detach() { __builtin_unreachable(); } bool joinable() const noexcept { __builtin_unreachable(); } id get_id() const noexcept { __builtin_unreachable(); }
    static unsigned hardware_concurrency() noexcept { __builtin_unreachable(); }
};
namespace this_thread { thread::id get_id() noexcept { __builtin_unreachable(); } void yield() noexcept { __builtin_unreachable(); } template <class D> void sleep_for(const D&) { __builtin_unreachable(); } }
} // namespace std
