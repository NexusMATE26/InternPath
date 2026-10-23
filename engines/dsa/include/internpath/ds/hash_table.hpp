#pragma once
#include "internpath/ds/dynamic_array.hpp"
#include "internpath/ds/singly_linked_list.hpp"
#include <cmath>
#include <cstddef>
#include <functional>
#include <initializer_list>
#include <stdexcept>
#include <utility>

namespace internpath::ds {

template<
    class Key,
    class Value,
    class Hash = std::hash<Key>,
    class KeyEqual = std::equal_to<Key>
>
class HashTable {
public:
    struct Entry {
        Key key;
        Value value;

        Entry(const Key& k, const Value& v) : key(k), value(v) {}
        Entry(Key&& k, Value&& v) : key(std::move(k)), value(std::move(v)) {}
        Entry(const Key& k, Value&& v) : key(k), value(std::move(v)) {}
        Entry(Key&& k, const Value& v) : key(std::move(k)), value(v) {}
    };

    using size_type = std::size_t;
    using Bucket = SinglyLinkedList<Entry>;
    using key_type = Key;
    using mapped_type = Value;
    using value_type = Entry;
    using hasher = Hash;
    using key_equal = KeyEqual;

    class const_iterator {
    public:
        using iterator_category = std::forward_iterator_tag;
        using value_type = Entry;
        using difference_type = std::ptrdiff_t;
        using pointer = const Entry*;
        using reference = const Entry&;

        const_iterator() = default;
        const_iterator(const DynamicArray<Bucket>* buckets, size_type bucket_idx, typename Bucket::const_iterator node_it)
            : buckets_(buckets), bucket_idx_(bucket_idx), node_it_(node_it) {
            advance_to_valid();
        }

        reference operator*() const { return *node_it_; }
        pointer operator->() const { return &(*node_it_); }

        const_iterator& operator++() {
            if (buckets_ && bucket_idx_ < buckets_->size()) {
                ++node_it_;
                advance_to_valid();
            }
            return *this;
        }

        const_iterator operator++(int) {
            const_iterator tmp = *this;
            ++(*this);
            return tmp;
        }

        bool operator==(const const_iterator& other) const {
            if (!buckets_ || bucket_idx_ >= buckets_->size()) {
                return !other.buckets_ || other.bucket_idx_ >= other.buckets_->size();
            }
            return buckets_ == other.buckets_ &&
                   bucket_idx_ == other.bucket_idx_ &&
                   node_it_ == other.node_it_;
        }

        bool operator!=(const const_iterator& other) const {
            return !(*this == other);
        }

    private:
        void advance_to_valid() {
            if (!buckets_) return;
            while (bucket_idx_ < buckets_->size()) {
                if (node_it_ != (*buckets_)[bucket_idx_].end()) {
                    return;
                }
                ++bucket_idx_;
                if (bucket_idx_ < buckets_->size()) {
                    node_it_ = (*buckets_)[bucket_idx_].begin();
                }
            }
        }

        const DynamicArray<Bucket>* buckets_ = nullptr;
        size_type bucket_idx_ = 0;
        typename Bucket::const_iterator node_it_{};
    };

    class iterator {
    public:
        using iterator_category = std::forward_iterator_tag;
        using value_type = Entry;
        using difference_type = std::ptrdiff_t;
        using pointer = Entry*;
        using reference = Entry&;

        iterator() = default;
        iterator(DynamicArray<Bucket>* buckets, size_type bucket_idx, typename Bucket::iterator node_it)
            : buckets_(buckets), bucket_idx_(bucket_idx), node_it_(node_it) {
            advance_to_valid();
        }

        reference operator*() const { return *node_it_; }
        pointer operator->() const { return &(*node_it_); }

        iterator& operator++() {
            if (buckets_ && bucket_idx_ < buckets_->size()) {
                ++node_it_;
                advance_to_valid();
            }
            return *this;
        }

        iterator operator++(int) {
            iterator tmp = *this;
            ++(*this);
            return tmp;
        }

        bool operator==(const iterator& other) const {
            if (!buckets_ || bucket_idx_ >= buckets_->size()) {
                return !other.buckets_ || other.bucket_idx_ >= other.buckets_->size();
            }
            return buckets_ == other.buckets_ &&
                   bucket_idx_ == other.bucket_idx_ &&
                   node_it_ == other.node_it_;
        }

        bool operator!=(const iterator& other) const {
            return !(*this == other);
        }

    private:
        void advance_to_valid() {
            if (!buckets_) return;
            while (bucket_idx_ < buckets_->size()) {
                if (node_it_ != (*buckets_)[bucket_idx_].end()) {
                    return;
                }
                ++bucket_idx_;
                if (bucket_idx_ < buckets_->size()) {
                    node_it_ = (*buckets_)[bucket_idx_].begin();
                }
            }
        }

        DynamicArray<Bucket>* buckets_ = nullptr;
        size_type bucket_idx_ = 0;
        typename Bucket::iterator node_it_{};
    };

    iterator begin() {
        if (buckets_.empty()) return end();
        return iterator(&buckets_, 0, buckets_[0].begin());
    }

    iterator end() {
        return iterator(&buckets_, buckets_.size(), typename Bucket::iterator());
    }

    const_iterator begin() const {
        if (buckets_.empty()) return end();
        return const_iterator(&buckets_, 0, buckets_[0].begin());
    }

    const_iterator end() const {
        return const_iterator(&buckets_, buckets_.size(), typename Bucket::const_iterator());
    }

    const_iterator cbegin() const { return begin(); }
    const_iterator cend() const { return end(); }

    static constexpr size_type kDefaultInitialBuckets = 16;
    static constexpr float kDefaultMaxLoadFactor = 0.75f;

    explicit HashTable(size_type initial_buckets = kDefaultInitialBuckets,
                       const Hash& hash = Hash(),
                       const KeyEqual& equal = KeyEqual())
        : buckets_(initial_buckets > 0 ? initial_buckets : kDefaultInitialBuckets),
          hash_(hash),
          key_equal_(equal),
          max_load_factor_(kDefaultMaxLoadFactor) {}

    HashTable(std::initializer_list<std::pair<Key, Value>> items)
        : HashTable() {
        for (const auto& item : items) {
            insert(item.first, item.second);
        }
    }

    HashTable(const HashTable& other)
        : buckets_(other.buckets_),
          size_(other.size_),
          hash_(other.hash_),
          key_equal_(other.key_equal_),
          max_load_factor_(other.max_load_factor_) {}

    HashTable(HashTable&& other) noexcept
        : buckets_(std::move(other.buckets_)),
          size_(other.size_),
          hash_(std::move(other.hash_)),
          key_equal_(std::move(other.key_equal_)),
          max_load_factor_(other.max_load_factor_) {
        other.size_ = 0;
    }

    HashTable& operator=(const HashTable& other) {
        if (this != &other) {
            HashTable tmp(other);
            swap(tmp);
        }
        return *this;
    }

    HashTable& operator=(HashTable&& other) noexcept {
        if (this != &other) {
            HashTable tmp(std::move(other));
            swap(tmp);
        }
        return *this;
    }

    ~HashTable() = default;

    size_type size() const noexcept { return size_; }
    bool empty() const noexcept { return size_ == 0; }
    size_type bucket_count() const noexcept { return buckets_.size(); }
    float max_load_factor() const noexcept { return max_load_factor_; }

    void max_load_factor(float mlf) {
        if (mlf <= 0.05f) throw std::invalid_argument("max_load_factor too small");
        max_load_factor_ = mlf;
        if (load_factor() > max_load_factor_) {
            rehash(static_cast<size_type>(std::ceil(static_cast<float>(size_) / max_load_factor_)));
        }
    }

    float load_factor() const noexcept {
        if (buckets_.empty()) return 0.0f;
        return static_cast<float>(size_) / static_cast<float>(buckets_.size());
    }

    size_type bucket_size(size_type idx) const {
        if (idx >= buckets_.size()) throw std::out_of_range("HashTable::bucket_size index out of range");
        return buckets_[idx].size();
    }

    size_type bucket(const Key& key) const noexcept {
        return bucket_index(key);
    }

    void clear() noexcept {
        for (size_type i = 0; i < buckets_.size(); ++i) {
            buckets_[i].clear();
        }
        size_ = 0;
    }

    void swap(HashTable& other) noexcept {
        using std::swap;
        buckets_.swap(other.buckets_);
        swap(size_, other.size_);
        swap(hash_, other.hash_);
        swap(key_equal_, other.key_equal_);
        swap(max_load_factor_, other.max_load_factor_);
    }

    void reserve(size_type count) {
        size_type needed_buckets = static_cast<size_type>(std::ceil(static_cast<float>(count) / max_load_factor_));
        if (needed_buckets > buckets_.size()) {
            rehash(needed_buckets);
        }
    }

    bool check_invariants() const noexcept {
        size_type total_entries = 0;
        for (size_type i = 0; i < buckets_.size(); ++i) {
            total_entries += buckets_[i].size();
            for (const auto& entry : buckets_[i]) {
                if (bucket_index(entry.key) != i) {
                    return false;
                }
            }
        }
        return total_entries == size_;
    }

    void rehash(size_type new_bucket_count) {
        if (new_bucket_count < 8) new_bucket_count = 8;
        size_type min_buckets = static_cast<size_type>(std::ceil(static_cast<float>(size_) / max_load_factor_));
        if (new_bucket_count < min_buckets) new_bucket_count = min_buckets;
        if (new_bucket_count == buckets_.size()) return;

        DynamicArray<Bucket> new_buckets(new_bucket_count);
        // Exception safety: stage all entries into new_buckets first.
        // If an allocation fails, buckets_ is completely untouched (strong guarantee).
        for (size_type i = 0; i < buckets_.size(); ++i) {
            for (const auto& entry : buckets_[i]) {
                size_type new_idx = hash_(entry.key) % new_bucket_count;
                new_buckets[new_idx].emplace_front(entry.key, entry.value);
            }
        }
        buckets_.swap(new_buckets);
    }

    std::pair<Value*, bool> insert(const Key& key, const Value& value) {
        ensure_capacity_for_insert();
        size_type idx = bucket_index(key);
        for (auto& entry : buckets_[idx]) {
            if (key_equal_(entry.key, key)) {
                return {&entry.value, false};
            }
        }
        buckets_[idx].emplace_front(key, value);
        ++size_;
        return {&buckets_[idx].front().value, true};
    }

    std::pair<Value*, bool> insert(Key&& key, Value&& value) {
        ensure_capacity_for_insert();
        size_type idx = bucket_index(key);
        for (auto& entry : buckets_[idx]) {
            if (key_equal_(entry.key, key)) {
                return {&entry.value, false};
            }
        }
        buckets_[idx].emplace_front(std::move(key), std::move(value));
        ++size_;
        return {&buckets_[idx].front().value, true};
    }

    template<class V>
    std::pair<Value*, bool> insert_or_assign(const Key& key, V&& value) {
        ensure_capacity_for_insert();
        size_type idx = bucket_index(key);
        for (auto& entry : buckets_[idx]) {
            if (key_equal_(entry.key, key)) {
                entry.value = std::forward<V>(value);
                return {&entry.value, false};
            }
        }
        buckets_[idx].emplace_front(key, std::forward<V>(value));
        ++size_;
        return {&buckets_[idx].front().value, true};
    }

    template<class V>
    std::pair<Value*, bool> insert_or_assign(Key&& key, V&& value) {
        ensure_capacity_for_insert();
        size_type idx = bucket_index(key);
        for (auto& entry : buckets_[idx]) {
            if (key_equal_(entry.key, key)) {
                entry.value = std::forward<V>(value);
                return {&entry.value, false};
            }
        }
        buckets_[idx].emplace_front(std::move(key), std::forward<V>(value));
        ++size_;
        return {&buckets_[idx].front().value, true};
    }

    Value* find(const Key& key) noexcept {
        if (size_ == 0 || buckets_.empty()) return nullptr;
        size_type idx = bucket_index(key);
        for (auto& entry : buckets_[idx]) {
            if (key_equal_(entry.key, key)) {
                return &entry.value;
            }
        }
        return nullptr;
    }

    const Value* find(const Key& key) const noexcept {
        if (size_ == 0 || buckets_.empty()) return nullptr;
        size_type idx = bucket_index(key);
        for (const auto& entry : buckets_[idx]) {
            if (key_equal_(entry.key, key)) {
                return &entry.value;
            }
        }
        return nullptr;
    }

    bool contains(const Key& key) const noexcept {
        return find(key) != nullptr;
    }

    bool erase(const Key& key) {
        if (size_ == 0 || buckets_.empty()) return false;
        size_type idx = bucket_index(key);
        bool removed = buckets_[idx].remove_first_if([this, &key](const Entry& e) {
            return key_equal_(e.key, key);
        });
        if (removed) {
            --size_;
            return true;
        }
        return false;
    }

    Value& operator[](const Key& key) {
        Value* v = find(key);
        if (v) return *v;
        return *insert(key, Value()).first;
    }

    // Collision metrics for DSA Lab analysis
    size_type collision_count() const noexcept {
        size_type collisions = 0;
        for (size_type i = 0; i < buckets_.size(); ++i) {
            if (buckets_[i].size() > 1) {
                collisions += (buckets_[i].size() - 1);
            }
        }
        return collisions;
    }

    size_type max_bucket_length() const noexcept {
        size_type max_len = 0;
        for (size_type i = 0; i < buckets_.size(); ++i) {
            if (buckets_[i].size() > max_len) {
                max_len = buckets_[i].size();
            }
        }
        return max_len;
    }

    size_type non_empty_buckets() const noexcept {
        size_type count = 0;
        for (size_type i = 0; i < buckets_.size(); ++i) {
            if (!buckets_[i].empty()) ++count;
        }
        return count;
    }

private:
    size_type bucket_index(const Key& key) const noexcept {
        return hash_(key) % buckets_.size();
    }

    void ensure_capacity_for_insert() {
        if (buckets_.empty()) {
            rehash(kDefaultInitialBuckets);
        } else if (static_cast<float>(size_ + 1) / static_cast<float>(buckets_.size()) > max_load_factor_) {
            rehash(buckets_.size() * 2);
        }
    }

    DynamicArray<Bucket> buckets_;
    size_type size_ = 0;
    Hash hash_;
    KeyEqual key_equal_;
    float max_load_factor_ = kDefaultMaxLoadFactor;
};

} // namespace internpath::ds
