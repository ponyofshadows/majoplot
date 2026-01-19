# LabelDict
随着内容的扩张，我应该把标签系统做成一个pythonic的类。
使用标签系统是为了在保持Data类的泛用性的同时表达实例的多样性。我不知道有没有更好的范式来做这件事。
- 它应该是一个Mapping,从标签名到值的映射。而且标签名是有序的。
- LabelDict应该包含一个Label:Value Mapping，一个用于生成摘要的Labels Tuple，一个SubGroup ID，用于应对后面提到的聚类上限问题。
- 标签名是简单的字符串。同标签名的多个标签是可比较和排序的
- 标签值包括数值、单位、单位后置Bool三部分，是可哈希的。数值可以是有理数或字符串
- 多个LabelDict可根据一个GroupRule(=Labels Tuple+一个整数成员上限，<=0代表无上限)聚类，机制是
  1. 挑选拥有Labels Tuple中所有Labels的LabelDict
  2. Labels的值比较相等的放同一Group，成员的SubGroup ID 都被设为0，除非达到成员数量上限
  3. 如果达到成员数量上限，则放新的SubGroup，SubGroup ID += 1，后面依此类推.
   > 这里可见SubGroup ID只是成员上限规则的派生量，同一Group不同SubGroup在聚类后会得到Label,Value完全相同的LabelDicts，必然会在下一轮分类中分到同一个Group，这时就重算SubGroup ID，所以完全不存在逻辑问题。
- 可以为一个LabelDict生成摘要（简单摘要只包含逗号分隔的带单位值，完全摘要还包含LabelName），如果SubGroupID不是默认的0，摘要中会带上它。 

如果一个标签所有实例都会拥有，且不参与group。则我认为应该直接作为属性。