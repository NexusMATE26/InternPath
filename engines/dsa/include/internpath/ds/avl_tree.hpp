#pragma once
#include "internpath/ds/dynamic_array.hpp"
#include <algorithm>
#include <cstddef>
#include <functional>
#include <initializer_list>
#include <stdexcept>
#include <utility>

namespace internpath::ds {

template<class Key, class Value, class Compare = std::less<Key>>
class AVLTree {
public:
    using size_type = std::size_t;
    using key_type = Key;
    using mapped_type = Value;
    using key_compare = Compare;

    struct Node {
        Key key;
        Value value;
        int height = 1;
        Node* left = nullptr;
        Node* right = nullptr;

        template<class K, class V>
        Node(K&& k, V&& v)
            : key(std::forward<K>(k)), value(std::forward<V>(v)), height(1), left(nullptr), right(nullptr) {}
    };

    struct RotationStats {
        size_type ll_rotations = 0;
        size_type rr_rotations = 0;
        size_type lr_rotations = 0;
        size_type rl_rotations = 0;

        size_type total() const noexcept {
            return ll_rotations + rr_rotations + lr_rotations + rl_rotations;
        }

        void reset() noexcept {
            ll_rotations = 0;
            rr_rotations = 0;
            lr_rotations = 0;
            rl_rotations = 0;
        }
    };

    explicit AVLTree(const Compare& comp = Compare())
        : compare_(comp), root_(nullptr), size_(0) {}

    AVLTree(std::initializer_list<std::pair<Key, Value>> items, const Compare& comp = Compare())
        : AVLTree(comp) {
        for (const auto& item : items) {
            insert(item.first, item.second);
        }
    }

    ~AVLTree() {
        clear();
    }

    AVLTree(const AVLTree& other)
        : compare_(other.compare_),
          root_(clone(other.root_)),
          size_(other.size_),
          stats_(other.stats_) {}

    AVLTree(AVLTree&& other) noexcept
        : compare_(std::move(other.compare_)),
          root_(other.root_),
          size_(other.size_),
          stats_(other.stats_) {
        other.root_ = nullptr;
        other.size_ = 0;
        other.stats_.reset();
    }

    AVLTree& operator=(const AVLTree& other) {
        if (this != &other) {
            AVLTree tmp(other);
            swap(tmp);
        }
        return *this;
    }

    AVLTree& operator=(AVLTree&& other) noexcept {
        if (this != &other) {
            AVLTree tmp(std::move(other));
            swap(tmp);
        }
        return *this;
    }

    void swap(AVLTree& other) noexcept {
        using std::swap;
        swap(root_, other.root_);
        swap(size_, other.size_);
        swap(compare_, other.compare_);
        swap(stats_, other.stats_);
    }

    size_type size() const noexcept { return size_; }
    bool empty() const noexcept { return size_ == 0; }
    int height() const noexcept { return node_height(root_); }
    RotationStats rotation_stats() const noexcept { return stats_; }
    void reset_rotation_stats() noexcept { stats_.reset(); }

    void clear() noexcept {
        delete_tree(root_);
        root_ = nullptr;
        size_ = 0;
    }

    std::pair<Value*, bool> insert(const Key& key, const Value& value) {
        bool inserted = false;
        Value* inserted_ptr = nullptr;
        root_ = insert_impl(root_, key, value, false, inserted, inserted_ptr);
        return {inserted_ptr, inserted};
    }

    std::pair<Value*, bool> insert(Key&& key, Value&& value) {
        bool inserted = false;
        Value* inserted_ptr = nullptr;
        root_ = insert_impl(root_, std::move(key), std::move(value), false, inserted, inserted_ptr);
        return {inserted_ptr, inserted};
    }

    template<class V>
    std::pair<Value*, bool> insert_or_assign(const Key& key, V&& value) {
        bool inserted = false;
        Value* target_ptr = nullptr;
        root_ = insert_impl(root_, key, std::forward<V>(value), true, inserted, target_ptr);
        return {target_ptr, inserted};
    }

    Value* find(const Key& key) noexcept {
        Node* curr = root_;
        while (curr) {
            if (compare_(key, curr->key)) {
                curr = curr->left;
            } else if (compare_(curr->key, key)) {
                curr = curr->right;
            } else {
                return &curr->value;
            }
        }
        return nullptr;
    }

    const Value* find(const Key& key) const noexcept {
        const Node* curr = root_;
        while (curr) {
            if (compare_(key, curr->key)) {
                curr = curr->left;
            } else if (compare_(curr->key, key)) {
                curr = curr->right;
            } else {
                return &curr->value;
            }
        }
        return nullptr;
    }

    bool contains(const Key& key) const noexcept {
        return find(key) != nullptr;
    }

    bool erase(const Key& key) {
        bool erased = false;
        root_ = erase_impl(root_, key, erased);
        return erased;
    }

    const Node* lower_bound(const Key& target) const noexcept {
        const Node* curr = root_;
        const Node* candidate = nullptr;
        while (curr) {
            if (!compare_(curr->key, target)) {
                candidate = curr;
                curr = curr->left;
            } else {
                curr = curr->right;
            }
        }
        return candidate;
    }

    Node* lower_bound(const Key& target) noexcept {
        Node* curr = root_;
        Node* candidate = nullptr;
        while (curr) {
            if (!compare_(curr->key, target)) {
                candidate = curr;
                curr = curr->left;
            } else {
                curr = curr->right;
            }
        }
        return candidate;
    }

    template<class Callback>
    void inorder_traversal(Callback&& cb) const {
        inorder_impl(root_, cb);
    }

    template<class Callback>
    void range_query(const Key& low, const Key& high, Callback&& cb) const {
        range_query_impl(root_, low, high, cb);
    }

    DynamicArray<std::pair<Key, Value>> range_query(const Key& low, const Key& high) const {
        DynamicArray<std::pair<Key, Value>> results;
        range_query_impl(root_, low, high, [&results](const Key& k, const Value& v) {
            results.emplace_back(k, v);
        });
        return results;
    }

    bool check_invariants() const {
        size_type count = 0;
        bool bst_ok = check_bst_and_balance(root_, nullptr, nullptr, count);
        return bst_ok && (count == size_);
    }

private:
    static int node_height(const Node* n) noexcept {
        return n ? n->height : 0;
    }

    static int balance_factor(const Node* n) noexcept {
        return n ? node_height(n->left) - node_height(n->right) : 0;
    }

    static void update_height(Node* n) noexcept {
        if (n) {
            n->height = 1 + std::max(node_height(n->left), node_height(n->right));
        }
    }

    Node* rotate_right(Node* y) {
        Node* x = y->left;
        Node* T2 = x->right;
        x->right = y;
        y->left = T2;
        update_height(y);
        update_height(x);
        ++stats_.ll_rotations;
        return x;
    }

    Node* rotate_left(Node* x) {
        Node* y = x->right;
        Node* T2 = y->left;
        y->left = x;
        x->right = T2;
        update_height(x);
        update_height(y);
        ++stats_.rr_rotations;
        return y;
    }

    Node* rotate_left_right(Node* z) {
        Node* y = z->left;
        Node* x = y->right;
        Node* T2 = x->left;
        y->right = T2;
        x->left = y;
        update_height(y);
        update_height(x);
        z->left = x;

        Node* T3 = x->right;
        x->right = z;
        z->left = T3;
        update_height(z);
        update_height(x);
        ++stats_.lr_rotations;
        return x;
    }

    Node* rotate_right_left(Node* z) {
        Node* y = z->right;
        Node* x = y->left;
        Node* T2 = x->right;
        y->left = T2;
        x->right = y;
        update_height(y);
        update_height(x);
        z->right = x;

        Node* T1 = x->left;
        x->left = z;
        z->right = T1;
        update_height(z);
        update_height(x);
        ++stats_.rl_rotations;
        return x;
    }

    Node* balance(Node* node) {
        if (!node) return nullptr;
        update_height(node);
        int bf = balance_factor(node);

        if (bf > 1) {
            if (balance_factor(node->left) >= 0) {
                return rotate_right(node);
            } else {
                return rotate_left_right(node);
            }
        }
        if (bf < -1) {
            if (balance_factor(node->right) <= 0) {
                return rotate_left(node);
            } else {
                return rotate_right_left(node);
            }
        }
        return node;
    }

    template<class K, class V>
    Node* insert_impl(Node* node, K&& key, V&& val, bool overwrite, bool& inserted, Value*& target_val) {
        if (!node) {
            Node* fresh = new Node(std::forward<K>(key), std::forward<V>(val));
            ++size_;
            inserted = true;
            target_val = &fresh->value;
            return fresh;
        }

        if (compare_(key, node->key)) {
            node->left = insert_impl(node->left, std::forward<K>(key), std::forward<V>(val), overwrite, inserted, target_val);
        } else if (compare_(node->key, key)) {
            node->right = insert_impl(node->right, std::forward<K>(key), std::forward<V>(val), overwrite, inserted, target_val);
        } else {
            inserted = false;
            if (overwrite) {
                node->value = std::forward<V>(val);
            }
            target_val = &node->value;
            return node;
        }

        return balance(node);
    }

    static Node* find_min(Node* node) noexcept {
        while (node && node->left) node = node->left;
        return node;
    }

    Node* erase_impl(Node* node, const Key& key, bool& erased) {
        if (!node) {
            erased = false;
            return nullptr;
        }

        if (compare_(key, node->key)) {
            node->left = erase_impl(node->left, key, erased);
        } else if (compare_(node->key, key)) {
            node->right = erase_impl(node->right, key, erased);
        } else {
            erased = true;
            if (!node->left && !node->right) {
                delete node;
                --size_;
                return nullptr;
            } else if (!node->left) {
                Node* right_child = node->right;
                delete node;
                --size_;
                return right_child;
            } else if (!node->right) {
                Node* left_child = node->left;
                delete node;
                --size_;
                return left_child;
            } else {
                Node* successor = find_min(node->right);
                node->key = successor->key;
                node->value = successor->value;
                bool dummy = false;
                node->right = erase_impl(node->right, successor->key, dummy);
            }
        }

        return balance(node);
    }

    template<class Callback>
    void inorder_impl(const Node* node, Callback&& cb) const {
        if (!node) return;
        inorder_impl(node->left, cb);
        cb(node->key, node->value);
        inorder_impl(node->right, cb);
    }

    template<class Callback>
    void range_query_impl(const Node* node, const Key& low, const Key& high, Callback&& cb) const {
        if (!node) return;
        if (compare_(low, node->key)) {
            range_query_impl(node->left, low, high, cb);
        }
        if (!compare_(node->key, low) && !compare_(high, node->key)) {
            cb(node->key, node->value);
        }
        if (compare_(node->key, high)) {
            range_query_impl(node->right, low, high, cb);
        }
    }

    bool check_bst_and_balance(const Node* node, const Key* min_key, const Key* max_key, size_type& count) const {
        if (!node) return true;
        ++count;
        if (min_key && !compare_(*min_key, node->key)) return false;
        if (max_key && !compare_(node->key, *max_key)) return false;

        int left_h = node_height(node->left);
        int right_h = node_height(node->right);
        int expected_h = 1 + std::max(left_h, right_h);
        if (node->height != expected_h) return false;

        int bf = left_h - right_h;
        if (bf < -1 || bf > 1) return false;

        return check_bst_and_balance(node->left, min_key, &node->key, count) &&
               check_bst_and_balance(node->right, &node->key, max_key, count);
    }

    static Node* clone(const Node* node) {
        if (!node) return nullptr;
        Node* copy = new Node(node->key, node->value);
        copy->height = node->height;
        try {
            copy->left = clone(node->left);
            copy->right = clone(node->right);
        } catch (...) {
            delete_tree(copy);
            throw;
        }
        return copy;
    }

    static void delete_tree(Node* node) noexcept {
        if (!node) return;
        delete_tree(node->left);
        delete_tree(node->right);
        delete node;
    }

    Compare compare_;
    Node* root_ = nullptr;
    size_type size_ = 0;
    RotationStats stats_;
};

} // namespace internpath::ds
